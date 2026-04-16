import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.device import Device
from app.models.enums import ColorMode, DeviceStatus, JobStatus, PaymentStatus, PrinterStatus
from app.models.print_job import PrintJob
from app.schemas.print_job import PrintJobCreateRequest, PrintJobCreateResponse
from app.services.pricing import compute_total_cost

router = APIRouter()


@router.post("", response_model=PrintJobCreateResponse)
def create_quote(payload: PrintJobCreateRequest, db: Session = Depends(get_db)) -> PrintJobCreateResponse:
    total = compute_total_cost(
        pages=payload.pages,
        copies=payload.copies,
        color=payload.color,
        bw_price_per_page=payload.bw_price_per_page,
        color_price_per_page=payload.color_price_per_page,
    )
    try:
        color_mode = ColorMode(payload.color)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported color mode '{payload.color}'.",
        ) from exc
    price_per_page = payload.color_price_per_page if color_mode == ColorMode.color else payload.bw_price_per_page

    target_device_code = payload.device_code.strip() or "prototype-local"
    device = db.query(Device).filter(Device.device_code == target_device_code).one_or_none()
    if device is None:
        device = Device(
            device_code=target_device_code,
            subdomain=target_device_code,
            site_name=f"Prototype Device ({target_device_code})",
            status=DeviceStatus.online,
            printer_status=PrinterStatus.ready,
            api_token_hash="prototype-token-hash",
            heartbeat_interval_sec=45,
            metadata_json={"mode": "prototype", "device_code": target_device_code},
            is_active=True,
        )
        db.add(device)
        db.flush()

    original_file_name = payload.original_file_name.strip() or "pending-upload.pdf"
    storage_key = (payload.storage_key or "").strip() or f"pending/{uuid.uuid4()}.pdf"

    job = PrintJob(
        device_id=device.id,
        original_file_name=original_file_name,
        storage_key=storage_key,
        file_sha256="0" * 64,
        file_size_bytes=1,
        pages=payload.pages,
        color=color_mode,
        copies=payload.copies,
        price_per_page=price_per_page,
        total_cost=total,
        currency=payload.currency.upper(),
        status=JobStatus.awaiting_payment,
        payment_status=PaymentStatus.initiated,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    return PrintJobCreateResponse(
        job_id=job.id,
        status=job.status.value,
        total_cost=total,
        currency=payload.currency,
    )
