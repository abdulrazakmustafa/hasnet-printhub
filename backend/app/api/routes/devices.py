from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.device import Device
from app.models.enums import DeviceStatus, JobStatus, PaymentStatus, PrinterStatus
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
        device.local_ip = payload.local_ip
        device.public_ip = payload.public_ip
        device.last_seen_at = now
        if payload.site_name:
            device.site_name = payload.site_name
        if payload.agent_version:
            device.agent_version = payload.agent_version
        if payload.firmware_version:
            device.firmware_version = payload.firmware_version

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
