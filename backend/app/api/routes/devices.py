from datetime import datetime, timezone
from email.message import EmailMessage
import smtplib

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models.admin_user import AdminUser
from app.models.alert import Alert
from app.models.device import Device
from app.models.enums import AlertSeverity, AlertStatus, AlertType, DeviceStatus, JobStatus, PaymentStatus, PrinterStatus
from app.models.log import LogEntry
from app.models.print_job import PrintJob
from app.schemas.common import APIMessage
from app.schemas.device import (
    DeviceHeartbeatRequest,
    DeviceHeartbeatResponse,
    DeviceJobStatusUpdateRequest,
    DeviceNextJobResponse,
)
from app.services.payment_gateway import sync_pending_payments
from app.services.upload_storage import delete_upload_artifacts, parse_upload_id_from_storage_key

router = APIRouter()


_PRINTER_ALERT_MAP: dict[str, tuple[AlertType, AlertSeverity, str]] = {
    "offline": (AlertType.printer_offline, AlertSeverity.critical, "Printer is offline"),
    "paper_out": (AlertType.paper_out, AlertSeverity.warning, "Printer is out of paper"),
    "paper_jam": (AlertType.printer_error, AlertSeverity.critical, "Printer has a paper jam"),
    "cover_open": (AlertType.printer_error, AlertSeverity.warning, "Printer cover is open"),
    "error": (AlertType.printer_error, AlertSeverity.critical, "Printer reported an error"),
    "queue_stuck": (AlertType.queue_stuck, AlertSeverity.warning, "Printer queue appears stuck"),
    "low_toner": (AlertType.printer_error, AlertSeverity.warning, "Printer toner is low"),
    "paused": (AlertType.printer_error, AlertSeverity.warning, "Printer is paused"),
    "unknown": (AlertType.printer_error, AlertSeverity.warning, "Printer status is unknown"),
}


def _safe_text(value: str | None, limit: int = 260) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _alert_dedupe_key(device_code: str, alert_type: AlertType) -> str:
    return f"{device_code}:{alert_type.value}"


def _build_active_alert_specs(payload: DeviceHeartbeatRequest) -> list[tuple[AlertType, AlertSeverity, str, str]]:
    specs: list[tuple[AlertType, AlertSeverity, str, str]] = []
    device_status = str(payload.status or "").strip().lower()
    printer_status = str(payload.printer_status or "").strip().lower()
    details = _safe_text(payload.printer_details or payload.active_error or "")

    if device_status in {"offline", "maintenance"}:
        title = f"Device status is {device_status}"
        specs.append((AlertType.device_offline, AlertSeverity.critical, title, details or title))

    printer_meta = _PRINTER_ALERT_MAP.get(printer_status)
    if printer_meta is not None:
        alert_type, severity, title = printer_meta
        specs.append((alert_type, severity, title, details or title))

    return specs


def _renotify_due(last_notified_at: datetime | None, now_utc: datetime) -> bool:
    if last_notified_at is None:
        return True
    if last_notified_at.tzinfo is None:
        last_notified_at = last_notified_at.replace(tzinfo=timezone.utc)
    else:
        last_notified_at = last_notified_at.astimezone(timezone.utc)
    delta_seconds = (now_utc - last_notified_at).total_seconds()
    return delta_seconds >= max(60, int(settings.alert_renotify_minutes) * 60)


def _send_alert_email(*, recipients: list[str], device: Device, alert: Alert) -> bool:
    smtp_host = str(settings.smtp_host or "").strip()
    smtp_from = str(settings.smtp_from or "").strip()
    if not smtp_host or not smtp_from or not recipients:
        return False

    message = EmailMessage()
    message["From"] = smtp_from
    message["To"] = ", ".join(recipients)
    message["Subject"] = f"[Hasnet PrintHub Alert] {alert.title} ({device.device_code})"
    message.set_content(
        "\n".join(
            [
                "Hasnet PrintHub raised a live device/printer alert.",
                "",
                f"Device: {device.device_code}",
                f"Site: {device.site_name}",
                f"Device status: {device.status.value}",
                f"Printer status: {device.printer_status.value}",
                f"Alert type: {alert.type.value}",
                f"Severity: {alert.severity.value}",
                f"Description: {alert.description or '-'}",
                f"First seen: {alert.first_seen_at.isoformat()}",
                f"Last seen: {alert.last_seen_at.isoformat()}",
                "",
                "Open admin panel for live details and action.",
            ]
        )
    )

    with smtplib.SMTP(host=smtp_host, port=settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
    return True


def _upsert_device_alerts(db: Session, *, device: Device, payload: DeviceHeartbeatRequest, now_utc: datetime) -> None:
    specs = _build_active_alert_specs(payload)
    active_by_type: dict[AlertType, tuple[AlertSeverity, str, str]] = {
        alert_type: (severity, title, description)
        for alert_type, severity, title, description in specs
    }
    alert_types_to_track = {AlertType.device_offline, AlertType.printer_offline, AlertType.paper_out, AlertType.printer_error, AlertType.queue_stuck}

    existing_alerts = db.execute(
        select(Alert).where(
            Alert.device_id == device.id,
            Alert.type.in_(list(alert_types_to_track)),
        )
    ).scalars().all()
    by_type: dict[AlertType, Alert] = {item.type: item for item in existing_alerts}
    recipients = [
        str(email).strip()
        for email in db.execute(select(AdminUser.email).where(AdminUser.is_active.is_(True))).scalars().all()
        if str(email).strip()
    ]

    for alert_type, (severity, title, description) in active_by_type.items():
        current = by_type.get(alert_type)
        if current is None:
            current = Alert(
                device_id=device.id,
                print_job_id=None,
                type=alert_type,
                severity=severity,
                status=AlertStatus.active,
                title=title,
                description=description,
                dedupe_key=_alert_dedupe_key(device.device_code, alert_type),
                first_seen_at=now_utc,
                last_seen_at=now_utc,
            )
            db.add(current)
            by_type[alert_type] = current
        else:
            current.severity = severity
            current.title = title
            current.description = description
            current.status = AlertStatus.active
            current.last_seen_at = now_utc
            current.resolved_at = None

        if _renotify_due(current.last_notified_at, now_utc):
            try:
                sent = _send_alert_email(recipients=recipients, device=device, alert=current)
            except Exception:
                sent = False
            if sent:
                current.last_notified_at = now_utc
                current.notify_count = int(current.notify_count or 0) + 1

    for alert_type in alert_types_to_track:
        if alert_type in active_by_type:
            continue
        current = by_type.get(alert_type)
        if current is None or current.status != AlertStatus.active:
            continue
        current.status = AlertStatus.resolved
        current.resolved_at = now_utc
        current.last_seen_at = now_utc


def _parse_device_status(value: str) -> DeviceStatus:
    normalized = value.strip().lower()
    try:
        return DeviceStatus(normalized)
    except ValueError:
        return DeviceStatus.degraded


def _parse_printer_status(value: str) -> PrinterStatus:
    normalized = value.strip().lower()
    try:
        return PrinterStatus(normalized)
    except ValueError:
        return PrinterStatus.unknown


@router.post("/heartbeat")
def device_heartbeat(
    payload: DeviceHeartbeatRequest, db: Session = Depends(get_db)
) -> DeviceHeartbeatResponse:
    now = payload.timestamp or datetime.now(timezone.utc)
    device = db.execute(select(Device).where(Device.device_code == payload.device_code)).scalar_one_or_none()
    if device is None:
        device = Device(
            device_code=payload.device_code,
            subdomain=payload.device_code,
            site_name=payload.site_name or payload.device_code,
            status=_parse_device_status(payload.status),
            printer_status=_parse_printer_status(payload.printer_status),
            printer_name=_safe_text(payload.printer_name, limit=255) or None,
            local_ip=payload.local_ip,
            public_ip=payload.public_ip,
            last_seen_at=now,
            heartbeat_interval_sec=45,
            api_token_hash="edge-bootstrap-token",
            agent_version=payload.agent_version,
            firmware_version=payload.firmware_version,
            metadata_json={"bootstrap": True},
            is_active=True,
        )
        db.add(device)
        db.flush()
    else:
        device.status = _parse_device_status(payload.status)
        device.printer_status = _parse_printer_status(payload.printer_status)
        if payload.printer_name is not None:
            device.printer_name = _safe_text(payload.printer_name, limit=255) or None
        device.local_ip = payload.local_ip
        device.public_ip = payload.public_ip
        device.last_seen_at = now
        if payload.site_name:
            device.site_name = payload.site_name
        if payload.agent_version:
            device.agent_version = payload.agent_version
        if payload.firmware_version:
            device.firmware_version = payload.firmware_version

    metadata = dict(device.metadata_json or {})
    if payload.uptime_seconds is not None:
        metadata["uptime_seconds"] = max(0, int(payload.uptime_seconds))
    if payload.boot_started_at is not None:
        metadata["boot_at"] = payload.boot_started_at.isoformat()
    metadata["last_heartbeat"] = {
        "printer_details": _safe_text(payload.printer_details, limit=1200) or None,
        "active_error": _safe_text(payload.active_error, limit=280) or None,
        "paper_level_pct": payload.paper_level_pct,
        "toner_level_pct": payload.toner_level_pct,
        "ink_level_pct": payload.ink_level_pct,
        "received_at": now.isoformat(),
    }
    device.metadata_json = metadata
    _upsert_device_alerts(db=db, device=device, payload=payload, now_utc=now)

    db.add(
        LogEntry(
            device_id=device.id,
            print_job_id=None,
            payment_id=None,
            level="info",
            event_type="device.heartbeat",
            message="Device heartbeat received.",
            payload={
                "status": payload.status,
                "printer_status": payload.printer_status,
                "printer_name": payload.printer_name,
                "printer_details": payload.printer_details,
                "active_error": payload.active_error,
                "uptime_seconds": payload.uptime_seconds,
                "boot_started_at": payload.boot_started_at.isoformat() if payload.boot_started_at else None,
                "local_ip": payload.local_ip,
                "public_ip": payload.public_ip,
            },
        )
    )
    db.commit()
    db.refresh(device)

    return DeviceHeartbeatResponse(
        status="received",
        device_code=device.device_code,
        device_status=device.status.value,
        printer_status=device.printer_status.value,
        heartbeat_at=now,
    )


@router.get("/{device_code}/next-job")
def get_next_job(device_code: str, db: Session = Depends(get_db)) -> DeviceNextJobResponse:
    device = db.execute(select(Device).where(Device.device_code == device_code)).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")

    # In local prototypes the webhook may be unreachable; sync pending provider payments on demand.
    sync_pending_payments(db, device_id=device.id, limit=10)

    job = (
        db.execute(
            select(PrintJob)
            .where(
                PrintJob.device_id == device.id,
                PrintJob.payment_status == PaymentStatus.confirmed,
                PrintJob.status.in_([JobStatus.paid, JobStatus.queued]),
            )
            .order_by(PrintJob.created_at.asc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if job is None:
        return DeviceNextJobResponse(status="no_job")

    if job.status in {JobStatus.paid, JobStatus.queued}:
        job.status = JobStatus.dispatched
        db.add(job)
        db.add(
            LogEntry(
                device_id=device.id,
                print_job_id=job.id,
                payment_id=None,
                level="info",
                event_type="job.dispatched",
                message="Job dispatched to edge device.",
                payload={"job_id": str(job.id)},
            )
        )
        db.commit()
        db.refresh(job)

    return DeviceNextJobResponse(
        status="assigned",
        job_id=str(job.id),
        storage_key=job.storage_key,
        original_file_name=job.original_file_name,
        copies=job.copies,
        color=job.color.value,
        pages=job.pages,
    )


@router.post("/{device_code}/jobs/{job_id}/status")
def update_job_status(
    device_code: str,
    job_id: str,
    payload: DeviceJobStatusUpdateRequest,
    db: Session = Depends(get_db),
) -> APIMessage:
    device = db.execute(select(Device).where(Device.device_code == device_code)).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")

    job = db.get(PrintJob, job_id)
    if job is None or job.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found for this device.")

    try:
        new_status = JobStatus(payload.status.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported job status '{payload.status}'.",
        ) from exc

    if new_status == JobStatus.printed:
        job.printed_at = datetime.now(timezone.utc)
        job.failure_reason = None
        upload_id = parse_upload_id_from_storage_key(job.storage_key)
        if upload_id:
            removed = delete_upload_artifacts(upload_id)
            db.add(
                LogEntry(
                    device_id=device.id,
                    print_job_id=job.id,
                    payment_id=None,
                    level="info",
                    event_type="job.upload.cleanup",
                    message="Removed uploaded PDF artifacts after successful print.",
                    payload={"upload_id": upload_id, "removed": removed},
                )
            )
    elif new_status == JobStatus.failed:
        job.failure_reason = payload.failure_reason or "Edge device reported job failure."

    job.status = new_status
    db.add(job)
    db.add(
        LogEntry(
            device_id=device.id,
            print_job_id=job.id,
            payment_id=None,
            level="info",
            event_type="job.status.update",
            message="Edge device updated job status.",
            payload={"status": new_status.value, "failure_reason": payload.failure_reason},
        )
    )
    db.commit()

    return APIMessage(status="ok", detail=f"Job status updated to {new_status.value}.")
