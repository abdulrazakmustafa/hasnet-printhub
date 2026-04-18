from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models.alert import Alert
from app.models.device import Device
from app.models.log import LogEntry
from app.models.enums import AlertStatus, DeviceStatus, JobStatus, PaymentMethod, PaymentStatus
from app.models.payment import Payment
from app.models.print_job import PrintJob
from app.services.customer_experience import (
    evaluate_customer_availability,
    get_customer_experience_config,
    save_customer_experience_config,
)
from app.services.device_actions import execute_local_device_action
from app.services.pricing_config import get_pricing_config, save_pricing_config
from app.services.payment_gateway import sync_pending_payments
from app.services.refund_workflow import (
    approve_refund_request,
    create_refund_request,
    execute_refund_request,
    list_refund_requests,
    reject_refund_request,
)

router = APIRouter()


class AdminPricingConfigResponse(BaseModel):
    bw_price_per_page: float
    color_price_per_page: float
    currency: str


class AdminPricingConfigUpdateRequest(BaseModel):
    bw_price_per_page: float = Field(..., ge=0)
    color_price_per_page: float = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)


class AdminCustomerExperienceUpdateRequest(BaseModel):
    payload: dict[str, Any]


class AdminDeviceActionRequest(BaseModel):
    action: str = Field(..., min_length=1, max_length=40)
    sudo_password: str = Field(default="", max_length=128)
    confirm_reboot: bool = False
    note: str = Field(default="", max_length=220)


class AdminRefundRequestCreate(BaseModel):
    payment_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, max_length=240)
    requested_by: str = Field(default="operator", min_length=1, max_length=80)


class AdminRefundDecisionRequest(BaseModel):
    actor: str = Field(default="operator", min_length=1, max_length=80)
    note: str = Field(default="", max_length=240)


def _parse_payment_status_filter(value: str | None) -> PaymentStatus | None:
    if value is not None and not isinstance(value, str):
        return None
    if not value or not value.strip():
        return None
    try:
        return PaymentStatus(value.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be one of: initiated, pending, confirmed, failed, expired, refunded",
        ) from exc


def _parse_payment_method_filter(value: str | None) -> PaymentMethod | None:
    if value is not None and not isinstance(value, str):
        return None
    if not value or not value.strip():
        return None
    try:
        return PaymentMethod(value.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="method must be one of: tigo, mpesa, airtel, snippe",
        ) from exc


def _parse_payment_lifecycle_filter(value: str | None) -> str | None:
    if value is not None and not isinstance(value, str):
        return None
    if not value or not value.strip():
        return None
    normalized = value.strip().lower()
    allowed = {
        "payment_confirmed_and_printed",
        "payment_confirmed_print_pending",
        "payment_pending",
        "payment_failed",
        "payment_refunded",
        "other",
    }
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "lifecycle must be one of: payment_confirmed_and_printed, "
                "payment_confirmed_print_pending, payment_pending, payment_failed, payment_refunded, other"
            ),
        )
    return normalized


def _derive_payment_lifecycle(payment: Payment, job: PrintJob) -> str:
    if payment.status == PaymentStatus.refunded:
        return "payment_refunded"
    if payment.status == PaymentStatus.confirmed and job.status == JobStatus.printed:
        return "payment_confirmed_and_printed"
    if payment.status == PaymentStatus.confirmed and job.status != JobStatus.printed:
        return "payment_confirmed_print_pending"
    if payment.status in {PaymentStatus.initiated, PaymentStatus.pending}:
        return "payment_pending"
    if payment.status in {PaymentStatus.failed, PaymentStatus.expired}:
        return "payment_failed"
    return "other"


def _pending_reference_time(payment: Payment, job: PrintJob) -> datetime:
    pending_since = payment.requested_at or job.created_at
    if pending_since.tzinfo is None:
        return pending_since.replace(tzinfo=timezone.utc)
    return pending_since.astimezone(timezone.utc)


def _pending_escalation_threshold_minutes() -> int:
    raw_value = getattr(settings, "customer_pending_escalation_minutes", 10)
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return 10
    return min(max(parsed, 1), 1440)


def _safe_text(value: object | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _safe_dict(value: object | None) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _extract_customer_name(payment: Payment) -> str | None:
    payload = _safe_dict(payment.provider_payload)
    request_payload = _safe_dict(payload.get("request"))
    customer_payload = _safe_dict(request_payload.get("customer"))
    first_name = _safe_text(customer_payload.get("firstname"))
    last_name = _safe_text(customer_payload.get("lastname"))
    if first_name or last_name:
        return " ".join(part for part in [first_name, last_name] if part)

    for key in ("CustomerName", "customer_name", "full_name", "name"):
        found = _safe_text(request_payload.get(key))
        if found:
            return found

    webhook_payload = _safe_dict(payload.get("last_webhook"))
    for key in ("CustomerName", "customer_name", "full_name", "name"):
        found = _safe_text(webhook_payload.get(key))
        if found:
            return found
    return None


def _extract_customer_msisdn(payment: Payment) -> str | None:
    payload = _safe_dict(payment.provider_payload)
    request_payload = _safe_dict(payload.get("request"))
    response_payload = _safe_dict(payload.get("response"))
    webhook_payload = _safe_dict(payload.get("last_webhook"))

    keys = ("phone_number", "CustomerMSISDN", "msisdn", "customer_msisdn", "MSISDN")
    for source in (request_payload, response_payload, webhook_payload):
        for key in keys:
            found = _safe_text(source.get(key))
            if found:
                return found
    return None


def _build_pending_incident_item(
    *,
    payment: Payment,
    job: PrintJob,
    resolved_device_code: str | None,
    now_utc: datetime,
) -> dict[str, Any]:
    pending_since = _pending_reference_time(payment, job)
    pending_minutes = max(0, int((now_utc - pending_since).total_seconds() // 60))
    threshold_minutes = _pending_escalation_threshold_minutes()
    escalated = pending_minutes >= threshold_minutes
    recommendation = (
        "Run reconcile and verify provider reference now; only retry after confirming prior attempt did not complete."
        if escalated
        else "Await provider confirmation, then run reconcile if still pending."
    )

    return {
        "payment_id": str(payment.id),
        "provider": payment.provider,
        "method": payment.method.value,
        "status": payment.status.value,
        "amount": float(payment.amount),
        "currency": payment.currency,
        "provider_request_id": payment.provider_request_id,
        "provider_transaction_ref": payment.provider_transaction_ref,
        "requested_at": payment.requested_at,
        "updated_at": payment.updated_at,
        "print_job_id": str(job.id),
        "print_job_status": job.status.value,
        "print_job_payment_status": job.payment_status.value,
        "device_code": resolved_device_code,
        "pending_minutes": pending_minutes,
        "escalation_threshold_minutes": threshold_minutes,
        "escalated": escalated,
        "recommended_action": recommendation,
    }


def _resolve_customer_device(db: Session, explicit_device_code: str | None = None) -> Device | None:
    config = get_customer_experience_config()
    selected_device_code = (explicit_device_code or config.get("active_device_code") or "").strip()
    if not selected_device_code:
        return None
    return db.execute(select(Device).where(Device.device_code == selected_device_code)).scalar_one_or_none()


def _device_customer_host(device: Device) -> str:
    metadata = device.metadata_json if isinstance(device.metadata_json, dict) else {}
    host_override = str(metadata.get("customer_host") or "").strip()
    if host_override:
        return host_override
    if device.local_ip:
        return str(device.local_ip)
    return f"{device.device_code}.local"


def _build_qr_pack(db: Session, *, explicit_device_code: str | None = None) -> dict[str, Any]:
    config = get_customer_experience_config()
    hotspot = config.get("hotspot", {})
    hotspot_enabled = bool(hotspot.get("enabled"))
    entry_path = str(hotspot.get("entry_path") or "/customer-start").strip() or "/customer-start"
    if not entry_path.startswith("/"):
        entry_path = "/" + entry_path

    device = _resolve_customer_device(db, explicit_device_code)
    if device is None:
        host = str(config.get("active_device_code") or "pi-kiosk-001") + ".local"
        resolved_device_code = str(config.get("active_device_code") or "pi-kiosk-001")
    else:
        host = _device_customer_host(device)
        resolved_device_code = device.device_code

    hotspot_gateway_ip = str(hotspot.get("gateway_ip") or "").strip()
    if hotspot_enabled and hotspot_gateway_ip:
        host = hotspot_gateway_ip

    entry_url = f"http://{host}:8000{entry_path}"
    wifi_security = str(hotspot.get("wifi_security") or "WPA").upper()
    wifi_ssid = str(hotspot.get("ssid") or "").strip()
    wifi_pass = str(hotspot.get("passphrase") or "").strip()
    wifi_qr_payload = ""
    if wifi_ssid:
        if wifi_security == "NOPASS":
            wifi_qr_payload = f"WIFI:T:nopass;S:{wifi_ssid};;"
        else:
            wifi_qr_payload = f"WIFI:T:{wifi_security};S:{wifi_ssid};P:{wifi_pass};;"

    return {
        "device_code": resolved_device_code,
        "entry_url": entry_url,
        "entry_path": entry_path,
        "wifi": {
            "enabled": hotspot_enabled,
            "ssid": wifi_ssid,
            "wifi_security": wifi_security,
            "gateway_ip": hotspot_gateway_ip,
            "wifi_qr_payload": wifi_qr_payload,
        },
        "notes": [
            "Use the entry_url QR for launching customer flow.",
            "If hotspot is enabled, print the Wi-Fi QR so customers connect to kiosk network first.",
        ],
    }


@router.get("/devices")
def admin_devices(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, object | None]]]:
    query = select(Device).order_by(Device.last_seen_at.desc().nullslast(), Device.created_at.desc())
    if not include_inactive:
        query = query.where(Device.is_active.is_(True))

    devices = db.execute(query).scalars().all()
    items: list[dict[str, object | None]] = []

    for device in devices:
        job_counts_row = db.execute(
            select(
                func.count(PrintJob.id).label("total_jobs"),
                func.sum(case((PrintJob.status == JobStatus.awaiting_payment, 1), else_=0)).label("awaiting_payment"),
                func.sum(
                    case(
                        (
                            PrintJob.status.in_([JobStatus.paid, JobStatus.queued, JobStatus.dispatched, JobStatus.printing]),
                            1,
                        ),
                        else_=0,
                    )
                ).label("in_progress"),
                func.sum(case((PrintJob.status == JobStatus.printed, 1), else_=0)).label("printed"),
                func.sum(case((PrintJob.status == JobStatus.failed, 1), else_=0)).label("failed"),
            ).where(PrintJob.device_id == device.id)
        ).one()

        active_alerts = (
            db.execute(
                select(func.count(Alert.id)).where(
                    Alert.device_id == device.id,
                    Alert.status == AlertStatus.active,
                )
            ).scalar_one()
            or 0
        )

        items.append(
            {
                "device_code": device.device_code,
                "site_name": device.site_name,
                "status": device.status.value,
                "printer_status": device.printer_status.value,
                "is_active": device.is_active,
                "last_seen_at": device.last_seen_at,
                "local_ip": device.local_ip,
                "public_ip": device.public_ip,
                "agent_version": device.agent_version,
                "firmware_version": device.firmware_version,
                "active_alerts": int(active_alerts),
                "jobs": {
                    "total": int(job_counts_row.total_jobs or 0),
                    "awaiting_payment": int(job_counts_row.awaiting_payment or 0),
                    "in_progress": int(job_counts_row.in_progress or 0),
                    "printed": int(job_counts_row.printed or 0),
                    "failed": int(job_counts_row.failed or 0),
                },
            }
        )

    return {"items": items}


@router.get("/payments")
def admin_payments(
    limit: int = Query(default=50, ge=1, le=200),
    payment_status: str | None = Query(default=None, alias="status"),
    method: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    device_code: str | None = Query(default=None),
    lifecycle: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    status_filter = _parse_payment_status_filter(payment_status)
    method_filter = _parse_payment_method_filter(method)
    lifecycle_filter = _parse_payment_lifecycle_filter(lifecycle)
    provider_filter = provider.strip().lower() if provider and provider.strip() else None
    device_filter = device_code.strip() if device_code and device_code.strip() else None

    query = (
        select(Payment, PrintJob, Device.device_code)
        .join(PrintJob, PrintJob.id == Payment.print_job_id)
        .join(Device, Device.id == PrintJob.device_id, isouter=True)
    )
    if status_filter is not None:
        query = query.where(Payment.status == status_filter)
    if method_filter is not None:
        query = query.where(Payment.method == method_filter)
    if provider_filter is not None:
        query = query.where(func.lower(Payment.provider) == provider_filter)
    if device_filter is not None:
        query = query.where(Device.device_code == device_filter)

    rows = db.execute(query.order_by(Payment.requested_at.desc(), Payment.created_at.desc()).limit(limit)).all()
    items = []
    for payment, job, resolved_device_code in rows:
        payment_lifecycle = _derive_payment_lifecycle(payment, job)
        if lifecycle_filter is not None and lifecycle_filter != payment_lifecycle:
            continue
        items.append(
            {
                "payment_id": str(payment.id),
                "requested_at": payment.requested_at,
                "confirmed_at": payment.confirmed_at,
                "updated_at": payment.updated_at,
                "provider": payment.provider,
                "method": payment.method.value,
                "status": payment.status.value,
                "amount": float(payment.amount),
                "currency": payment.currency,
                "provider_request_id": payment.provider_request_id,
                "provider_transaction_ref": payment.provider_transaction_ref,
                "customer_name": _extract_customer_name(payment),
                "customer_msisdn": _extract_customer_msisdn(payment),
                "failure_code": payment.failure_code,
                "failure_message": payment.failure_message,
                "print_job_id": str(job.id),
                "print_job_status": job.status.value,
                "print_job_payment_status": job.payment_status.value,
                "document_name": job.original_file_name,
                "pages": int(job.pages),
                "copies": int(job.copies),
                "color_mode": job.color.value,
                "device_code": resolved_device_code,
                "lifecycle": payment_lifecycle,
            }
        )

    return {"items": items, "count": len(items)}


@router.get("/payments/pending-incidents")
def admin_pending_payment_incidents(
    limit: int = Query(default=50, ge=1, le=200),
    escalated_only: bool = Query(default=False),
    method: str | None = Query(default=None),
    device_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    method_filter = _parse_payment_method_filter(method)
    device_filter = device_code.strip() if device_code and device_code.strip() else None
    now_utc = datetime.now(timezone.utc)

    query = (
        select(Payment, PrintJob, Device.device_code)
        .join(PrintJob, PrintJob.id == Payment.print_job_id)
        .join(Device, Device.id == PrintJob.device_id, isouter=True)
        .where(
            Payment.status == PaymentStatus.pending,
            PrintJob.payment_status == PaymentStatus.pending,
        )
        .order_by(Payment.requested_at.asc(), Payment.created_at.asc())
        .limit(limit)
    )

    if method_filter is not None:
        query = query.where(Payment.method == method_filter)
    if device_filter is not None:
        query = query.where(Device.device_code == device_filter)

    rows = db.execute(query).all()
    items: list[dict[str, Any]] = []
    escalated_count = 0
    for payment, job, resolved_device_code in rows:
        incident = _build_pending_incident_item(
            payment=payment,
            job=job,
            resolved_device_code=resolved_device_code,
            now_utc=now_utc,
        )
        if incident["escalated"]:
            escalated_count += 1
        if escalated_only and not incident["escalated"]:
            continue
        items.append(incident)

    return {
        "items": items,
        "count": len(items),
        "escalated_count": escalated_count,
        "escalation_threshold_minutes": _pending_escalation_threshold_minutes(),
    }


@router.get("/dashboard/snapshot")
def admin_dashboard_snapshot(
    recent_payments_limit: int = Query(default=10, ge=1, le=50),
    pending_incidents_limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    generated_at_utc = datetime.now(timezone.utc)
    report = admin_report_today(db=db)
    recent_payments = admin_payments(
        limit=recent_payments_limit,
        payment_status=None,
        method=None,
        provider=None,
        device_code=None,
        lifecycle=None,
        db=db,
    )
    pending_incidents = admin_pending_payment_incidents(
        limit=pending_incidents_limit,
        escalated_only=False,
        method=None,
        device_code=None,
        db=db,
    )
    pricing = get_pricing_config()

    return {
        "generated_at_utc": generated_at_utc,
        "window": report["window"],
        "kpis": {
            "confirmed_payments_today": report["payments"]["confirmed"],
            "confirmed_amount_today": report["payments"]["confirmed_amount"],
            "printed_jobs_today": report["jobs"]["printed"],
            "active_devices": report["devices"]["active"],
            "online_devices": report["devices"]["online"],
            "active_alerts": report["alerts"]["active"],
            "pending_incidents": pending_incidents["count"],
            "escalated_pending_incidents": pending_incidents["escalated_count"],
        },
        "report_today": report,
        "pricing": pricing,
        "pending_incidents": pending_incidents,
        "recent_payments": {
            "count": recent_payments["count"],
            "items": recent_payments["items"],
        },
    }


@router.get("/pricing", response_model=AdminPricingConfigResponse)
def admin_get_pricing_config() -> AdminPricingConfigResponse:
    payload = get_pricing_config()
    return AdminPricingConfigResponse(**payload)


@router.put("/pricing", response_model=AdminPricingConfigResponse)
def admin_update_pricing_config(payload: AdminPricingConfigUpdateRequest) -> AdminPricingConfigResponse:
    currency = payload.currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="currency must be a 3-letter ISO code, for example TZS.",
        )

    saved = save_pricing_config(
        bw_price_per_page=payload.bw_price_per_page,
        color_price_per_page=payload.color_price_per_page,
        currency=currency,
    )
    return AdminPricingConfigResponse(**saved)


@router.get("/customer-experience")
def admin_get_customer_experience() -> dict[str, Any]:
    return get_customer_experience_config()


@router.put("/customer-experience")
def admin_update_customer_experience(payload: AdminCustomerExperienceUpdateRequest) -> dict[str, Any]:
    return save_customer_experience_config(payload.payload)


@router.get("/customer-availability")
def admin_customer_availability(
    device_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    config = get_customer_experience_config()
    device = _resolve_customer_device(db, device_code)
    availability = evaluate_customer_availability(device=device, config=config)
    selected_device_code = device.device_code if device else str(config.get("active_device_code") or "")
    return {
        "device_code": selected_device_code,
        "availability": availability,
        "operations": config.get("operations", {}),
    }


@router.get("/devices/{device_code}/qr-pack")
def admin_device_qr_pack(device_code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _build_qr_pack(db, explicit_device_code=device_code)


@router.post("/devices/{device_code}/actions")
def admin_device_action(
    device_code: str,
    payload: AdminDeviceActionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    device = db.execute(select(Device).where(Device.device_code == device_code)).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")

    action = payload.action.strip().lower()
    if action in {"pause_kiosk", "resume_kiosk"}:
        config = get_customer_experience_config()
        ops = config.get("operations", {})
        if action == "pause_kiosk":
            ops["uploads_enabled"] = False
            ops["payments_enabled"] = False
            if payload.note.strip():
                ops["pause_reason"] = payload.note.strip()
        else:
            ops["uploads_enabled"] = True
            ops["payments_enabled"] = True
            ops["pause_reason"] = ""
        config["operations"] = ops
        save_customer_experience_config(config)
        db.add(
            LogEntry(
                device_id=device.id,
                print_job_id=None,
                payment_id=None,
                level="warning",
                event_type="device.kiosk_pause_toggle",
                message=f"Kiosk action '{action}' triggered by admin.",
                payload={"action": action, "note": payload.note.strip() or None},
            )
        )
        db.commit()
        return {"status": "ok", "action": action, "detail": "Kiosk operation flags updated."}

    local_device_code = str(get_customer_experience_config().get("active_device_code") or "").strip()
    if device.device_code != local_device_code:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This backend can execute service-level actions only for the active local kiosk. "
                "Use that kiosk's local admin panel for restart/reboot."
            ),
        )

    result = execute_local_device_action(
        action=action,
        sudo_password=payload.sudo_password,
        confirm_reboot=payload.confirm_reboot,
    )
    db.add(
        LogEntry(
            device_id=device.id,
            print_job_id=None,
            payment_id=None,
            level="warning" if result["ok"] else "error",
            event_type="device.control.action",
            message=f"Device action '{action}' executed from admin.",
            payload={
                "action": action,
                "ok": bool(result["ok"]),
                "code": result["code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "note": payload.note.strip() or None,
            },
        )
    )
    db.commit()
    return {
        "status": "ok" if result["ok"] else "failed",
        "action": action,
        "result": result,
    }


@router.get("/refunds")
def admin_list_refunds(
    payment_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    items = list_refund_requests(payment_id=payment_id, status_filter=status_filter)
    return {"items": items, "count": len(items)}


@router.post("/refunds/request")
def admin_create_refund_request(payload: AdminRefundRequestCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = create_refund_request(
        db=db,
        payment_id=payload.payment_id,
        reason=payload.reason,
        requested_by=payload.requested_by,
    )
    return {"status": "ok", "item": item}


@router.post("/refunds/{refund_id}/approve")
def admin_approve_refund(
    refund_id: str,
    payload: AdminRefundDecisionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    item = approve_refund_request(
        db=db,
        refund_id=refund_id,
        approved_by=payload.actor,
        note=payload.note,
    )
    return {"status": "ok", "item": item}


@router.post("/refunds/{refund_id}/reject")
def admin_reject_refund(
    refund_id: str,
    payload: AdminRefundDecisionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    item = reject_refund_request(
        db=db,
        refund_id=refund_id,
        rejected_by=payload.actor,
        note=payload.note,
    )
    return {"status": "ok", "item": item}


@router.post("/refunds/{refund_id}/execute")
def admin_execute_refund(
    refund_id: str,
    payload: AdminRefundDecisionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    item = execute_refund_request(
        db=db,
        refund_id=refund_id,
        executed_by=payload.actor,
        note=payload.note,
    )
    return {"status": "ok", "item": item}


@router.get("/reports/today")
def admin_report_today(db: Session = Depends(get_db)) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    day_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_utc = day_start_utc + timedelta(days=1)

    payments_row = db.execute(
        select(
            func.count(Payment.id).label("total"),
            func.sum(case((Payment.status == PaymentStatus.confirmed, 1), else_=0)).label("confirmed"),
            func.sum(case((Payment.status == PaymentStatus.pending, 1), else_=0)).label("pending"),
            func.sum(case((Payment.status == PaymentStatus.failed, 1), else_=0)).label("failed"),
            func.sum(case((Payment.status == PaymentStatus.expired, 1), else_=0)).label("expired"),
            func.coalesce(
                func.sum(case((Payment.status == PaymentStatus.confirmed, Payment.amount), else_=0)),
                0,
            ).label("confirmed_amount"),
        ).where(Payment.requested_at >= day_start_utc, Payment.requested_at < day_end_utc)
    ).one()

    jobs_row = db.execute(
        select(
            func.count(PrintJob.id).label("total"),
            func.sum(case((PrintJob.status == JobStatus.awaiting_payment, 1), else_=0)).label("awaiting_payment"),
            func.sum(case((PrintJob.status == JobStatus.printed, 1), else_=0)).label("printed"),
            func.sum(case((PrintJob.status == JobStatus.failed, 1), else_=0)).label("failed"),
            func.sum(
                case(
                    (PrintJob.status.in_([JobStatus.paid, JobStatus.queued, JobStatus.dispatched, JobStatus.printing]), 1),
                    else_=0,
                )
            ).label("in_progress"),
        ).where(PrintJob.created_at >= day_start_utc, PrintJob.created_at < day_end_utc)
    ).one()

    devices_row = db.execute(
        select(
            func.sum(case((Device.is_active.is_(True), 1), else_=0)).label("active"),
            func.sum(case((Device.status == DeviceStatus.online, 1), else_=0)).label("online"),
        )
    ).one()

    active_alerts = db.execute(select(func.count(Alert.id)).where(Alert.status == AlertStatus.active)).scalar_one() or 0

    return {
        "window": {
            "start_utc": day_start_utc,
            "end_utc": day_end_utc,
        },
        "payments": {
            "total": int(payments_row.total or 0),
            "confirmed": int(payments_row.confirmed or 0),
            "pending": int(payments_row.pending or 0),
            "failed": int(payments_row.failed or 0),
            "expired": int(payments_row.expired or 0),
            "confirmed_amount": float(payments_row.confirmed_amount or 0),
        },
        "jobs": {
            "total": int(jobs_row.total or 0),
            "awaiting_payment": int(jobs_row.awaiting_payment or 0),
            "in_progress": int(jobs_row.in_progress or 0),
            "printed": int(jobs_row.printed or 0),
            "failed": int(jobs_row.failed or 0),
        },
        "devices": {
            "active": int(devices_row.active or 0),
            "online": int(devices_row.online or 0),
        },
        "alerts": {
            "active": int(active_alerts),
        },
    }


@router.post("/payments/reconcile")
def admin_reconcile_payments(
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    synced = sync_pending_payments(db, limit=limit)
    return {"status": "ok", "synced": synced, "limit": limit}
