from datetime import datetime, timedelta, timezone
from io import BytesIO
import subprocess
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_db, require_admin_or_super_admin
from app.core.config import settings
from app.models.alert import Alert
from app.models.device import Device
from app.models.log import LogEntry
from app.models.enums import AlertSeverity, AlertStatus, DeviceStatus, JobStatus, PaymentMethod, PaymentStatus
from app.models.payment import Payment
from app.models.print_job import PrintJob
from app.services.customer_experience import (
    evaluate_customer_availability,
    get_customer_experience_config,
    resolve_printer_capabilities,
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

try:
    import qrcode
except Exception:  # pragma: no cover - optional dependency for runtime
    qrcode = None

router = APIRouter(dependencies=[Depends(get_current_admin_user)])


class AdminPricingConfigResponse(BaseModel):
    bw_price_per_page: float
    color_price_per_page: float
    a4_bw_price_per_page: float
    a4_color_price_per_page: float
    a3_bw_price_per_page: float
    a3_color_price_per_page: float
    currency: str


class AdminPricingConfigUpdateRequest(BaseModel):
    bw_price_per_page: float | None = Field(default=None, ge=0)
    color_price_per_page: float | None = Field(default=None, ge=0)
    a4_bw_price_per_page: float | None = Field(default=None, ge=0)
    a4_color_price_per_page: float | None = Field(default=None, ge=0)
    a3_bw_price_per_page: float | None = Field(default=None, ge=0)
    a3_color_price_per_page: float | None = Field(default=None, ge=0)
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


def _normalize_device_code(device_code: str | None) -> str | None:
    normalized = str(device_code or "").strip()
    return normalized or None


def _parse_datetime(value: object | None) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _estimate_uptime_hours(device: Device, now_utc: datetime) -> float:
    metadata = device.metadata_json if isinstance(device.metadata_json, dict) else {}

    for key in ("uptime_seconds", "uptime_sec", "agent_uptime_seconds"):
        raw_value = metadata.get(key)
        try:
            seconds = float(raw_value)
        except (TypeError, ValueError):
            continue
        if seconds > 0:
            return round(seconds / 3600.0, 2)

    started_at = None
    for key in ("agent_started_at", "boot_at", "boot_time", "uptime_started_at"):
        started_at = _parse_datetime(metadata.get(key))
        if started_at is not None:
            break

    if started_at is None:
        started_at = device.created_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        else:
            started_at = started_at.astimezone(timezone.utc)

    hours = max(0.0, (now_utc - started_at).total_seconds() / 3600.0)
    return round(hours, 2)


def _build_device_monitor(db: Session, device_code: str | None) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    since_24h_utc = now_utc - timedelta(hours=24)
    selected_device = _normalize_device_code(device_code)

    device_query = select(Device).where(Device.is_active.is_(True))
    if selected_device is not None:
        device_query = device_query.where(Device.device_code == selected_device)
    devices = db.execute(
        device_query.order_by(Device.last_seen_at.desc().nullslast(), Device.created_at.desc())
    ).scalars().all()

    items: list[dict[str, Any]] = []
    total_uptime = 0.0
    total_errors_24h = 0
    total_active_alerts = 0
    online_count = 0

    for device in devices:
        uptime_hours = _estimate_uptime_hours(device, now_utc=now_utc)
        metadata = device.metadata_json if isinstance(device.metadata_json, dict) else {}
        if device.status == DeviceStatus.online:
            online_count += 1

        active_alerts = (
            db.execute(
                select(func.count(Alert.id)).where(
                    Alert.device_id == device.id,
                    Alert.status == AlertStatus.active,
                )
            ).scalar_one()
            or 0
        )
        alerts_24h = (
            db.execute(
                select(func.count(Alert.id)).where(
                    Alert.device_id == device.id,
                    Alert.last_seen_at >= since_24h_utc,
                    Alert.severity.in_([AlertSeverity.warning, AlertSeverity.critical]),
                )
            ).scalar_one()
            or 0
        )
        failed_jobs_24h = (
            db.execute(
                select(func.count(PrintJob.id)).where(
                    PrintJob.device_id == device.id,
                    PrintJob.status == JobStatus.failed,
                    PrintJob.created_at >= since_24h_utc,
                )
            ).scalar_one()
            or 0
        )

        error_events_24h = int(alerts_24h) + int(failed_jobs_24h)
        total_uptime += float(uptime_hours)
        total_errors_24h += error_events_24h
        total_active_alerts += int(active_alerts)
        heartbeat_meta = (
            metadata.get("last_heartbeat", {})
            if isinstance(metadata.get("last_heartbeat"), dict)
            else {}
        )

        items.append(
            {
                "device_code": device.device_code,
                "status": device.status.value,
                "printer_status": device.printer_status.value,
                "printer_name": device.printer_name,
                "last_seen_at": device.last_seen_at,
                "uptime_hours": float(uptime_hours),
                "active_alerts": int(active_alerts),
                "failed_jobs_24h": int(failed_jobs_24h),
                "error_events_24h": int(error_events_24h),
                "printer_details": heartbeat_meta.get("printer_details"),
                "active_error": heartbeat_meta.get("active_error"),
                "paper_level_pct": heartbeat_meta.get("paper_level_pct"),
                "toner_level_pct": heartbeat_meta.get("toner_level_pct"),
                "ink_level_pct": heartbeat_meta.get("ink_level_pct"),
            }
        )

    count = len(items)
    return {
        "device_count": count,
        "summary": {
            "avg_uptime_hours": round(total_uptime / count, 2) if count > 0 else 0.0,
            "total_error_events_24h": int(total_errors_24h),
            "total_active_alerts": int(total_active_alerts),
            "online_devices": int(online_count),
        },
        "devices": items,
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


def _escape_wifi_qr(value: str) -> str:
    escaped = value
    for token in ("\\", ";", ",", ":", '"'):
        escaped = escaped.replace(token, "\\" + token)
    return escaped


def _gateway_ip_is_active(gateway_ip: str) -> bool:
    candidate = str(gateway_ip or "").strip()
    if not candidate:
        return False
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("inet "):
            continue
        # line format: inet 10.55.0.1/24 brd ...
        raw = line.replace("inet ", "", 1).split(" ", 1)[0]
        ip = raw.split("/", 1)[0]
        if ip == candidate:
            return True
    return False


def _build_qr_pack(db: Session, *, explicit_device_code: str | None = None) -> dict[str, Any]:
    config = get_customer_experience_config()
    hotspot = config.get("hotspot", {})
    hotspot_enabled = bool(hotspot.get("enabled"))
    hotspot_gateway_ip = str(hotspot.get("gateway_ip") or "").strip()
    hotspot_active = hotspot_enabled and _gateway_ip_is_active(hotspot_gateway_ip)
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

    lan_host = host
    if hotspot_active and hotspot_gateway_ip:
        host = hotspot_gateway_ip

    entry_url = f"http://{host}:8000{entry_path}"
    lan_entry_url = f"http://{lan_host}:8000{entry_path}"
    wifi_security = str(hotspot.get("wifi_security") or "WPA").upper()
    wifi_ssid = str(hotspot.get("ssid") or "").strip()
    wifi_pass = str(hotspot.get("passphrase") or "").strip()
    wifi_qr_payload = ""
    if wifi_ssid:
        escaped_ssid = _escape_wifi_qr(wifi_ssid)
        if wifi_security == "NOPASS":
            wifi_qr_payload = f"WIFI:T:nopass;S:{escaped_ssid};;"
        else:
            escaped_pass = _escape_wifi_qr(wifi_pass)
            wifi_qr_payload = f"WIFI:T:{wifi_security};S:{escaped_ssid};P:{escaped_pass};;"

    notes = [
        "Use the entry_url QR for launching customer flow.",
        "If hotspot is enabled, print the Wi-Fi QR so customers connect to kiosk network first.",
        "The hotspot URL (10.55.0.1) works only after joining the kiosk hotspot Wi-Fi.",
    ]
    if hotspot_enabled and not hotspot_active:
        notes.insert(
            0,
            "Hotspot is configured but not currently active on this Pi. Entry URL has been switched to LAN host automatically.",
        )

    return {
        "device_code": resolved_device_code,
        "entry_url": entry_url,
        "lan_entry_url": lan_entry_url,
        "entry_path": entry_path,
        "wifi": {
            "enabled": hotspot_enabled,
            "active": hotspot_active,
            "ssid": wifi_ssid,
            "wifi_security": wifi_security,
            "gateway_ip": hotspot_gateway_ip,
            "wifi_qr_payload": wifi_qr_payload,
        },
        "notes": notes,
    }


@router.get("/devices")
def admin_devices(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, object | None]]]:
    query = select(Device).order_by(Device.last_seen_at.desc().nullslast(), Device.created_at.desc())
    if not include_inactive:
        query = query.where(Device.is_active.is_(True))

    config = get_customer_experience_config()
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
                "printer_name": device.printer_name,
                "is_active": device.is_active,
                "last_seen_at": device.last_seen_at,
                "local_ip": device.local_ip,
                "public_ip": device.public_ip,
                "agent_version": device.agent_version,
                "firmware_version": device.firmware_version,
                "printer_capabilities": resolve_printer_capabilities(config=config, device_code=device.device_code),
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
    recent_payments_limit: int = Query(default=50, ge=1, le=200),
    pending_incidents_limit: int = Query(default=25, ge=1, le=200),
    device_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    selected_device = _normalize_device_code(device_code)
    generated_at_utc = datetime.now(timezone.utc)
    report = admin_report_today(device_code=selected_device, db=db)
    recent_payments = admin_payments(
        limit=recent_payments_limit,
        payment_status=None,
        method=None,
        provider=None,
        device_code=selected_device,
        lifecycle=None,
        db=db,
    )
    pending_incidents = admin_pending_payment_incidents(
        limit=pending_incidents_limit,
        escalated_only=False,
        method=None,
        device_code=selected_device,
        db=db,
    )
    monitor = _build_device_monitor(db=db, device_code=selected_device)
    pricing = get_pricing_config()

    return {
        "generated_at_utc": generated_at_utc,
        "device_code": selected_device,
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
        "monitor": monitor,
        "pricing": pricing,
        "pending_incidents": pending_incidents,
        "recent_payments": {
            "count": recent_payments["count"],
            "items": recent_payments["items"],
        },
    }


@router.get("/pricing", response_model=AdminPricingConfigResponse)
def admin_get_pricing_config(_manager=Depends(require_admin_or_super_admin)) -> AdminPricingConfigResponse:
    payload = get_pricing_config()
    return AdminPricingConfigResponse(**payload)


@router.put("/pricing", response_model=AdminPricingConfigResponse)
def admin_update_pricing_config(
    payload: AdminPricingConfigUpdateRequest,
    _manager=Depends(require_admin_or_super_admin),
) -> AdminPricingConfigResponse:
    currency = payload.currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="currency must be a 3-letter ISO code, for example TZS.",
        )

    legacy_bw = float(payload.bw_price_per_page if payload.bw_price_per_page is not None else 500.0)
    legacy_color = float(payload.color_price_per_page if payload.color_price_per_page is not None else 500.0)
    a4_bw = float(payload.a4_bw_price_per_page if payload.a4_bw_price_per_page is not None else legacy_bw)
    a4_color = float(payload.a4_color_price_per_page if payload.a4_color_price_per_page is not None else legacy_color)
    a3_bw = float(payload.a3_bw_price_per_page if payload.a3_bw_price_per_page is not None else a4_bw)
    a3_color = float(payload.a3_color_price_per_page if payload.a3_color_price_per_page is not None else a4_color)

    saved = save_pricing_config(
        bw_price_per_page=legacy_bw,
        color_price_per_page=legacy_color,
        a4_bw_price_per_page=a4_bw,
        a4_color_price_per_page=a4_color,
        a3_bw_price_per_page=a3_bw,
        a3_color_price_per_page=a3_color,
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
    printer_capabilities = resolve_printer_capabilities(config=config, device_code=selected_device_code)
    return {
        "device_code": selected_device_code,
        "availability": availability,
        "operations": config.get("operations", {}),
        "printer_capabilities": printer_capabilities,
    }


@router.get("/devices/{device_code}/qr-pack")
def admin_device_qr_pack(device_code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _build_qr_pack(db, explicit_device_code=device_code)


@router.get("/qr-code")
def admin_qr_code_image(
    data: str = Query(..., min_length=1, max_length=2000),
    box_size: int = Query(default=8, ge=2, le=16),
) -> Response:
    if qrcode is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="QR image generator dependency is not installed on this backend.",
        )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")
    out = BytesIO()
    image.save(out, format="PNG")
    return Response(content=out.getvalue(), media_type="image/png")


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
        hotspot_config=get_customer_experience_config().get("hotspot") if action == "apply_hotspot" else None,
    )
    if action in {"apply_hotspot", "disable_hotspot"} and result["ok"]:
        config = get_customer_experience_config()
        hotspot_cfg = config.get("hotspot", {})
        hotspot_cfg["enabled"] = action == "apply_hotspot"
        config["hotspot"] = hotspot_cfg
        save_customer_experience_config(config)
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
    _manager=Depends(require_admin_or_super_admin),
) -> dict[str, Any]:
    items = list_refund_requests(payment_id=payment_id, status_filter=status_filter)
    return {"items": items, "count": len(items)}


@router.post("/refunds/request")
def admin_create_refund_request(
    payload: AdminRefundRequestCreate,
    db: Session = Depends(get_db),
    _manager=Depends(require_admin_or_super_admin),
) -> dict[str, Any]:
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
    _manager=Depends(require_admin_or_super_admin),
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
    _manager=Depends(require_admin_or_super_admin),
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
    _manager=Depends(require_admin_or_super_admin),
) -> dict[str, Any]:
    item = execute_refund_request(
        db=db,
        refund_id=refund_id,
        executed_by=payload.actor,
        note=payload.note,
    )
    return {"status": "ok", "item": item}


@router.get("/reports/today")
def admin_report_today(
    device_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    selected_device = _normalize_device_code(device_code)
    now_utc = datetime.now(timezone.utc)
    day_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_utc = day_start_utc + timedelta(days=1)

    payments_stmt = (
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
        )
        .select_from(Payment)
        .where(Payment.requested_at >= day_start_utc, Payment.requested_at < day_end_utc)
    )
    if selected_device is not None:
        payments_stmt = (
            payments_stmt.join(PrintJob, PrintJob.id == Payment.print_job_id)
            .join(Device, Device.id == PrintJob.device_id)
            .where(Device.device_code == selected_device)
        )
    payments_row = db.execute(payments_stmt).one()

    jobs_stmt = (
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
        )
        .select_from(PrintJob)
        .where(PrintJob.created_at >= day_start_utc, PrintJob.created_at < day_end_utc)
    )
    if selected_device is not None:
        jobs_stmt = jobs_stmt.join(Device, Device.id == PrintJob.device_id).where(Device.device_code == selected_device)
    jobs_row = db.execute(jobs_stmt).one()

    devices_stmt = (
        select(
            func.sum(case((Device.is_active.is_(True), 1), else_=0)).label("active"),
            func.sum(case((Device.status == DeviceStatus.online, 1), else_=0)).label("online"),
        )
        .select_from(Device)
    )
    if selected_device is not None:
        devices_stmt = devices_stmt.where(Device.device_code == selected_device)
    devices_row = db.execute(devices_stmt).one()

    alerts_stmt = select(func.count(Alert.id)).where(Alert.status == AlertStatus.active)
    if selected_device is not None:
        alerts_stmt = alerts_stmt.join(Device, Device.id == Alert.device_id).where(Device.device_code == selected_device)
    active_alerts = db.execute(alerts_stmt).scalar_one() or 0

    return {
        "device_code": selected_device,
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


@router.get("/reports/history")
def admin_report_history(
    days: int = Query(default=90, ge=30, le=180),
    device_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    selected_device = _normalize_device_code(device_code)
    now_utc = datetime.now(timezone.utc)
    window_start_utc = (now_utc - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    window_end_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    retention_days = 90
    retention_cutoff_utc = now_utc - timedelta(days=retention_days)

    payments_stmt = (
        select(
            func.date_trunc("day", Payment.requested_at).label("day"),
            func.count(Payment.id).label("total"),
            func.sum(case((Payment.status == PaymentStatus.confirmed, 1), else_=0)).label("confirmed"),
            func.coalesce(
                func.sum(case((Payment.status == PaymentStatus.confirmed, Payment.amount), else_=0)),
                0,
            ).label("confirmed_amount"),
        )
        .select_from(Payment)
        .where(Payment.requested_at >= window_start_utc, Payment.requested_at < window_end_utc)
    )
    if selected_device is not None:
        payments_stmt = (
            payments_stmt.join(PrintJob, PrintJob.id == Payment.print_job_id)
            .join(Device, Device.id == PrintJob.device_id)
            .where(Device.device_code == selected_device)
        )
    payments_rows = db.execute(payments_stmt.group_by("day").order_by("day")).all()

    jobs_stmt = (
        select(
            func.date_trunc("day", PrintJob.created_at).label("day"),
            func.count(PrintJob.id).label("total"),
            func.sum(case((PrintJob.status == JobStatus.printed, 1), else_=0)).label("printed"),
            func.sum(case((PrintJob.status == JobStatus.failed, 1), else_=0)).label("failed"),
        )
        .select_from(PrintJob)
        .where(PrintJob.created_at >= window_start_utc, PrintJob.created_at < window_end_utc)
    )
    if selected_device is not None:
        jobs_stmt = jobs_stmt.join(Device, Device.id == PrintJob.device_id).where(Device.device_code == selected_device)
    jobs_rows = db.execute(jobs_stmt.group_by("day").order_by("day")).all()

    alerts_stmt = (
        select(
            func.date_trunc("day", Alert.last_seen_at).label("day"),
            func.count(Alert.id).label("total"),
            func.sum(case((Alert.severity == AlertSeverity.critical, 1), else_=0)).label("critical"),
            func.sum(case((Alert.status == AlertStatus.active, 1), else_=0)).label("active"),
        )
        .select_from(Alert)
        .where(Alert.last_seen_at >= window_start_utc, Alert.last_seen_at < window_end_utc)
    )
    if selected_device is not None:
        alerts_stmt = alerts_stmt.join(Device, Device.id == Alert.device_id).where(Device.device_code == selected_device)
    alerts_rows = db.execute(alerts_stmt.group_by("day").order_by("day")).all()

    series: dict[str, dict[str, Any]] = {}
    for index in range(days):
        point_day = window_start_utc + timedelta(days=index)
        key = point_day.date().isoformat()
        series[key] = {
            "date": key,
            "payments_total": 0,
            "payments_confirmed": 0,
            "confirmed_amount": 0.0,
            "jobs_total": 0,
            "jobs_printed": 0,
            "jobs_failed": 0,
            "alerts_total": 0,
            "alerts_critical": 0,
            "alerts_active": 0,
        }

    for day, total, confirmed, confirmed_amount in payments_rows:
        key = day.date().isoformat()
        if key not in series:
            continue
        series[key]["payments_total"] = int(total or 0)
        series[key]["payments_confirmed"] = int(confirmed or 0)
        series[key]["confirmed_amount"] = float(confirmed_amount or 0)

    for day, total, printed, failed in jobs_rows:
        key = day.date().isoformat()
        if key not in series:
            continue
        series[key]["jobs_total"] = int(total or 0)
        series[key]["jobs_printed"] = int(printed or 0)
        series[key]["jobs_failed"] = int(failed or 0)

    for day, total, critical, active in alerts_rows:
        key = day.date().isoformat()
        if key not in series:
            continue
        series[key]["alerts_total"] = int(total or 0)
        series[key]["alerts_critical"] = int(critical or 0)
        series[key]["alerts_active"] = int(active or 0)

    logs_old_stmt = select(func.count(LogEntry.id)).where(LogEntry.created_at < retention_cutoff_utc)
    resolved_alerts_old_stmt = select(func.count(Alert.id)).where(
        Alert.status == AlertStatus.resolved,
        Alert.last_seen_at < retention_cutoff_utc,
    )
    jobs_old_stmt = select(func.count(PrintJob.id)).where(PrintJob.created_at < retention_cutoff_utc)
    payments_old_stmt = select(func.count(Payment.id)).where(Payment.requested_at < retention_cutoff_utc)

    if selected_device is not None:
        logs_old_stmt = logs_old_stmt.join(Device, Device.id == LogEntry.device_id).where(Device.device_code == selected_device)
        resolved_alerts_old_stmt = resolved_alerts_old_stmt.join(Device, Device.id == Alert.device_id).where(
            Device.device_code == selected_device
        )
        jobs_old_stmt = jobs_old_stmt.join(Device, Device.id == PrintJob.device_id).where(Device.device_code == selected_device)
        payments_old_stmt = (
            payments_old_stmt.join(PrintJob, PrintJob.id == Payment.print_job_id)
            .join(Device, Device.id == PrintJob.device_id)
            .where(Device.device_code == selected_device)
        )

    return {
        "device_code": selected_device,
        "window": {
            "days": days,
            "start_utc": window_start_utc,
            "end_utc": window_end_utc,
        },
        "retention": {
            "days": retention_days,
            "cutoff_utc": retention_cutoff_utc,
            "cleanup_candidates": {
                "logs": int(db.execute(logs_old_stmt).scalar_one() or 0),
                "resolved_alerts": int(db.execute(resolved_alerts_old_stmt).scalar_one() or 0),
                "print_jobs": int(db.execute(jobs_old_stmt).scalar_one() or 0),
                "payments": int(db.execute(payments_old_stmt).scalar_one() or 0),
            },
            "cleanup_scope": [
                "Logs and resolved alerts can be cleaned up safely from admin panel.",
                "Payments and print jobs are audit-critical and should be archived before deletion.",
            ],
        },
        "daily": [series[key] for key in sorted(series.keys())],
    }


@router.post("/reports/cleanup")
def admin_cleanup_reports_data(
    retention_days: int = Query(default=90, ge=30, le=365),
    dry_run: bool = Query(default=False),
    device_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    selected_device = _normalize_device_code(device_code)
    cutoff_utc = datetime.now(timezone.utc) - timedelta(days=retention_days)

    log_filter = [LogEntry.created_at < cutoff_utc]
    alert_filter = [
        Alert.status == AlertStatus.resolved,
        Alert.last_seen_at < cutoff_utc,
    ]

    if selected_device is not None:
        device_id = db.execute(select(Device.id).where(Device.device_code == selected_device)).scalar_one_or_none()
        if device_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found for cleanup scope.")
        log_filter.append(LogEntry.device_id == device_id)
        alert_filter.append(Alert.device_id == device_id)

    logs_count = int(db.execute(select(func.count(LogEntry.id)).where(*log_filter)).scalar_one() or 0)
    alerts_count = int(db.execute(select(func.count(Alert.id)).where(*alert_filter)).scalar_one() or 0)

    if dry_run:
        return {
            "status": "dry_run",
            "device_code": selected_device,
            "retention_days": retention_days,
            "cutoff_utc": cutoff_utc,
            "delete_candidates": {
                "logs": logs_count,
                "resolved_alerts": alerts_count,
            },
        }

    logs_deleted = db.execute(delete(LogEntry).where(*log_filter)).rowcount or 0
    alerts_deleted = db.execute(delete(Alert).where(*alert_filter)).rowcount or 0
    db.commit()
    return {
        "status": "ok",
        "device_code": selected_device,
        "retention_days": retention_days,
        "cutoff_utc": cutoff_utc,
        "deleted": {
            "logs": int(logs_deleted),
            "resolved_alerts": int(alerts_deleted),
        },
    }


@router.post("/payments/reconcile")
def admin_reconcile_payments(
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    synced = sync_pending_payments(db, limit=limit)
    return {"status": "ok", "synced": synced, "limit": limit}
