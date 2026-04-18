from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models.alert import Alert
from app.models.device import Device
from app.models.enums import AlertStatus, DeviceStatus, JobStatus, PaymentMethod, PaymentStatus
from app.models.payment import Payment
from app.models.print_job import PrintJob
from app.services.payment_gateway import sync_pending_payments

router = APIRouter()


def _parse_payment_status_filter(value: str | None) -> PaymentStatus | None:
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
    if not value or not value.strip():
        return None
    try:
        return PaymentMethod(value.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="method must be one of: tigo, mpesa, airtel, snippe",
        ) from exc


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
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    status_filter = _parse_payment_status_filter(payment_status)
    method_filter = _parse_payment_method_filter(method)
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
                "failure_code": payment.failure_code,
                "failure_message": payment.failure_message,
                "print_job_id": str(job.id),
                "print_job_status": job.status.value,
                "print_job_payment_status": job.payment_status.value,
                "device_code": resolved_device_code,
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
        db=db,
    )
    pending_incidents = admin_pending_payment_incidents(
        limit=pending_incidents_limit,
        escalated_only=False,
        method=None,
        device_code=None,
        db=db,
    )

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
        "pending_incidents": pending_incidents,
        "recent_payments": {
            "count": recent_payments["count"],
            "items": recent_payments["items"],
        },
    }


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
