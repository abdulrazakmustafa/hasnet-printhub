import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.device import Device
from app.models.enums import ColorMode, DeviceStatus, JobStatus, PaymentStatus, PrinterStatus
from app.models.payment import Payment
from app.models.print_job import PrintJob
from app.schemas.print_job import PrintJobCreateRequest, PrintJobCreateResponse, PrintJobCustomerStatusResponse
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


@router.get("/{job_id}/customer-status", response_model=PrintJobCustomerStatusResponse)
def get_customer_job_status(job_id: str, db: Session = Depends(get_db)) -> PrintJobCustomerStatusResponse:
    try:
        parsed_job_id = uuid.UUID(job_id.strip())
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid job id '{job_id}'.",
        ) from exc

    job = db.get(PrintJob, parsed_job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print job not found.")

    latest_payment = (
        db.execute(
            select(Payment)
            .where(Payment.print_job_id == job.id)
            .order_by(Payment.requested_at.desc(), Payment.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )

    stage = "awaiting_payment"
    message = "Waiting for payment confirmation."
    next_action = "Approve payment prompt on phone or contact operator if delayed."

    if job.payment_status == PaymentStatus.confirmed:
        if job.status == JobStatus.printed:
            stage = "completed"
            message = "Payment confirmed and document printed."
            next_action = "Collect your document."
        elif job.status in {JobStatus.paid, JobStatus.queued, JobStatus.dispatched, JobStatus.printing}:
            stage = "processing"
            message = "Payment confirmed. Your document is being processed for printing."
            next_action = "Please wait while the kiosk completes printing."
        else:
            stage = "payment_confirmed"
            message = "Payment confirmed."
            next_action = "Operator should verify printer dispatch/queue state."
    elif job.payment_status in {PaymentStatus.failed, PaymentStatus.expired}:
        stage = "payment_failed"
        message = "Payment was not successful."
        next_action = "Retry with a new payment transaction."
    elif job.payment_status == PaymentStatus.pending:
        stage = "payment_pending"
        message = "Payment is pending provider confirmation."
        next_action = "Wait briefly, then operator can reconcile and recheck status."

    return PrintJobCustomerStatusResponse(
        job_id=job.id,
        stage=stage,
        message=message,
        next_action=next_action,
        job_status=job.status.value,
        payment_status=job.payment_status.value,
        payment_method=job.payment_method.value if job.payment_method else None,
        transaction_reference=job.transaction_reference,
        total_cost=float(job.total_cost),
        currency=job.currency,
        pages=job.pages,
        copies=job.copies,
        color=job.color.value,
        provider=latest_payment.provider if latest_payment else None,
        provider_request_id=latest_payment.provider_request_id if latest_payment else None,
        provider_transaction_ref=latest_payment.provider_transaction_ref if latest_payment else None,
        created_at=job.created_at,
        paid_at=job.paid_at,
        printed_at=job.printed_at,
        failure_reason=job.failure_reason,
    )
