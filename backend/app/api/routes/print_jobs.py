import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.device import Device
from app.models.enums import ColorMode, DeviceStatus, JobStatus, PaymentStatus, PrinterStatus
from app.models.payment import Payment
from app.models.print_job import PrintJob
from app.schemas.print_job import (
    CustomerPaymentReceipt,
    CustomerTimelineEvent,
    PrintJobCreateRequest,
    PrintJobCreateResponse,
    PrintJobCustomerReceiptResponse,
    PrintJobCustomerStatusResponse,
)
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


def _parse_job_id_or_422(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(job_id.strip())
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid job id '{job_id}'.",
        ) from exc


def _load_job_or_404(db: Session, parsed_job_id: uuid.UUID) -> PrintJob:
    job = db.get(PrintJob, parsed_job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print job not found.")
    return job


def _load_latest_payment(db: Session, job_id: uuid.UUID) -> Payment | None:
    return (
        db.execute(
            select(Payment)
            .where(Payment.print_job_id == job_id)
            .order_by(Payment.requested_at.desc(), Payment.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def _resolve_customer_stage(job: PrintJob) -> tuple[str, str, str]:
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

    return stage, message, next_action


def _build_customer_receipt(payment: Payment | None) -> CustomerPaymentReceipt | None:
    if payment is None:
        return None

    return CustomerPaymentReceipt(
        payment_id=payment.id,
        provider=payment.provider,
        provider_request_id=payment.provider_request_id,
        provider_transaction_ref=payment.provider_transaction_ref,
        payment_status=payment.status.value,
        amount=float(payment.amount),
        currency=payment.currency,
        requested_at=payment.requested_at,
        confirmed_at=payment.confirmed_at,
        webhook_received_at=payment.webhook_received_at,
        updated_at=payment.updated_at,
    )


def _build_customer_timeline(job: PrintJob, payment: Payment | None) -> list[CustomerTimelineEvent]:
    events: list[CustomerTimelineEvent] = [
        CustomerTimelineEvent(
            code="job_created",
            label="Document uploaded",
            state="done",
            at=job.created_at,
            detail="Print job created and waiting for payment.",
        )
    ]

    provider_ref = payment.provider_request_id if payment and payment.provider_request_id else None
    payment_request_detail = (
        f"Payment request created ({provider_ref})." if provider_ref else "Payment request created."
    )
    events.append(
        CustomerTimelineEvent(
            code="payment_requested",
            label="Payment requested",
            state="done" if payment is not None else "pending",
            at=payment.requested_at if payment else None,
            detail=payment_request_detail if payment else "Waiting for payment initiation.",
        )
    )

    confirmation_state = "pending"
    confirmation_detail = "Waiting for provider payment confirmation."
    if job.payment_status == PaymentStatus.confirmed:
        confirmation_state = "done"
        confirmation_detail = "Payment confirmed."
    elif job.payment_status in {PaymentStatus.failed, PaymentStatus.expired}:
        confirmation_state = "blocked"
        confirmation_detail = "Payment failed or expired."
    elif job.payment_status == PaymentStatus.pending:
        confirmation_state = "current"
    events.append(
        CustomerTimelineEvent(
            code="payment_confirmed",
            label="Payment confirmation",
            state=confirmation_state,
            at=job.paid_at or (payment.confirmed_at if payment else None),
            detail=confirmation_detail,
        )
    )

    dispatch_state = "pending"
    dispatch_detail = "Printer dispatch starts after payment confirmation."
    if job.status in {JobStatus.dispatched, JobStatus.printing, JobStatus.printed}:
        dispatch_state = "done" if job.status == JobStatus.printed else "current"
        dispatch_detail = "Print job dispatched to kiosk printer."
    elif job.status in {JobStatus.paid, JobStatus.queued}:
        dispatch_state = "current"
        dispatch_detail = "Payment confirmed. Dispatch queue in progress."
    elif job.status == JobStatus.failed:
        dispatch_state = "blocked"
        dispatch_detail = "Dispatch interrupted due to print failure."
    events.append(
        CustomerTimelineEvent(
            code="print_dispatched",
            label="Printer dispatch",
            state=dispatch_state,
            at=job.paid_at,
            detail=dispatch_detail,
        )
    )

    completion_state = "pending"
    completion_detail = "Waiting for printer completion."
    if job.status == JobStatus.printed:
        completion_state = "done"
        completion_detail = "Printing completed successfully."
    elif job.status == JobStatus.failed:
        completion_state = "blocked"
        completion_detail = job.failure_reason or "Printer reported failure."
    elif job.status in {JobStatus.printing, JobStatus.dispatched, JobStatus.queued, JobStatus.paid}:
        completion_state = "current"
    events.append(
        CustomerTimelineEvent(
            code="print_completed",
            label="Printing completed",
            state=completion_state,
            at=job.printed_at,
            detail=completion_detail,
        )
    )

    return events


@router.get("/{job_id}/customer-status", response_model=PrintJobCustomerStatusResponse)
def get_customer_job_status(job_id: str, db: Session = Depends(get_db)) -> PrintJobCustomerStatusResponse:
    parsed_job_id = _parse_job_id_or_422(job_id)
    job = _load_job_or_404(db, parsed_job_id)
    latest_payment = _load_latest_payment(db, job.id)

    stage, message, next_action = _resolve_customer_stage(job)
    timeline = _build_customer_timeline(job, latest_payment)
    receipt = _build_customer_receipt(latest_payment)

    return PrintJobCustomerStatusResponse(
        contract_version="customer-status-v1",
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
        timeline=timeline,
        receipt=receipt,
    )


@router.get("/{job_id}/customer-receipt", response_model=PrintJobCustomerReceiptResponse)
def get_customer_receipt(job_id: str, db: Session = Depends(get_db)) -> PrintJobCustomerReceiptResponse:
    parsed_job_id = _parse_job_id_or_422(job_id)
    job = _load_job_or_404(db, parsed_job_id)
    latest_payment = _load_latest_payment(db, job.id)

    stage, message, next_action = _resolve_customer_stage(job)
    timeline = _build_customer_timeline(job, latest_payment)
    receipt = _build_customer_receipt(latest_payment)

    headline = "Payment/Print Receipt"
    if stage == "completed":
        headline = "Payment Success and Print Completed"
    elif stage == "processing":
        headline = "Payment Success - Printing In Progress"
    elif stage == "payment_failed":
        headline = "Payment Not Successful"
    elif stage == "payment_pending":
        headline = "Payment Pending Confirmation"

    return PrintJobCustomerReceiptResponse(
        contract_version="customer-receipt-v1",
        job_id=job.id,
        stage=stage,
        headline=headline,
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
        issued_at=datetime.now(timezone.utc),
        timeline=timeline,
        receipt=receipt,
    )
