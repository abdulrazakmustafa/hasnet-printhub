from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.device import Device
from app.models.enums import JobStatus, PaymentStatus
from app.models.payment import Payment
from app.models.print_job import PrintJob
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentRetrySafeCreateResponse,
    PaymentStatusSnapshotResponse,
)
from app.services.payment_gateway import (
    create_payment as create_provider_payment,
    handle_mixx_webhook,
    handle_snippe_webhook,
    sync_pending_payments,
)

router = APIRouter()


@router.post("/create", response_model=PaymentCreateResponse)
def create_payment(payload: PaymentCreateRequest, db: Session = Depends(get_db)) -> PaymentCreateResponse:
    return create_provider_payment(payload=payload, db=db)


def _load_print_job_or_404(db: Session, print_job_id) -> PrintJob:
    print_job = db.get(PrintJob, print_job_id)
    if print_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print job not found.")
    return print_job


def _latest_payment_for_job(db: Session, print_job_id) -> Payment | None:
    return (
        db.execute(
            select(Payment)
            .where(Payment.print_job_id == print_job_id)
            .order_by(Payment.requested_at.desc(), Payment.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def _retry_block_reason_or_none(print_job: PrintJob, latest_payment: Payment | None) -> str | None:
    if print_job.payment_status == PaymentStatus.confirmed:
        return "Payment already confirmed for this print job. No retry is needed."

    if print_job.status in {
        JobStatus.paid,
        JobStatus.queued,
        JobStatus.dispatched,
        JobStatus.printing,
        JobStatus.printed,
    }:
        return "Print job is already paid or in print workflow. Retry is blocked."

    if latest_payment is None:
        return None

    if latest_payment.status == PaymentStatus.pending:
        pending_ref = latest_payment.provider_request_id or "unknown"
        return (
            "Latest payment is still pending after reconcile "
            f"(provider_request_id={pending_ref}). Do not retry yet."
        )

    if latest_payment.status == PaymentStatus.confirmed:
        confirmed_ref = latest_payment.provider_request_id or "unknown"
        return f"Latest payment is already confirmed (provider_request_id={confirmed_ref}). Retry is not allowed."

    return None


@router.post("/retry-safe", response_model=PaymentRetrySafeCreateResponse)
def retry_safe_create_payment(
    payload: PaymentCreateRequest,
    reconcile_limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaymentRetrySafeCreateResponse:
    if reconcile_limit < 1 or reconcile_limit > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="reconcile_limit must be between 1 and 100.",
        )

    print_job = _load_print_job_or_404(db, payload.print_job_id)
    synced = sync_pending_payments(db, device_id=print_job.device_id, limit=reconcile_limit)
    db.refresh(print_job)

    latest_payment = _latest_payment_for_job(db, payload.print_job_id)
    block_reason = _retry_block_reason_or_none(print_job, latest_payment)
    if block_reason:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=block_reason)

    created = create_provider_payment(payload=payload, db=db)
    return PaymentRetrySafeCreateResponse(
        decision="created_new_payment",
        reconcile_synced=synced,
        payment=created,
    )


@router.post("/webhook/snippe")
async def snippe_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    raw_body = await request.body()
    handle_snippe_webhook(raw_body=raw_body, headers=request.headers, db=db)
    return {"status": "accepted"}


@router.post("/webhook/mixx")
async def mixx_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    raw_body = await request.body()
    return handle_mixx_webhook(raw_body=raw_body, headers=request.headers, db=db)


@router.get("/by-provider-ref/{provider_request_id}", response_model=PaymentStatusSnapshotResponse)
def get_payment_by_provider_ref(
    provider_request_id: str, db: Session = Depends(get_db)
) -> PaymentStatusSnapshotResponse:
    normalized_ref = provider_request_id.strip()
    if not normalized_ref:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="provider_request_id must not be empty.",
        )

    payment = (
        db.execute(
            select(Payment)
            .where(Payment.provider_request_id == normalized_ref)
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No payment found for provider_request_id '{normalized_ref}'.",
        )

    print_job = db.get(PrintJob, payment.print_job_id)
    device = db.get(Device, print_job.device_id) if print_job is not None else None

    return PaymentStatusSnapshotResponse(
        payment_id=payment.id,
        provider=payment.provider,
        provider_request_id=payment.provider_request_id or normalized_ref,
        provider_transaction_ref=payment.provider_transaction_ref,
        payment_status=payment.status.value,
        payment_amount=float(payment.amount),
        payment_currency=payment.currency,
        payment_requested_at=payment.requested_at,
        payment_confirmed_at=payment.confirmed_at,
        payment_webhook_received_at=payment.webhook_received_at,
        payment_updated_at=payment.updated_at,
        print_job_id=print_job.id if print_job else None,
        print_job_status=print_job.status.value if print_job else None,
        print_job_payment_status=print_job.payment_status.value if print_job else None,
        print_job_paid_at=print_job.paid_at if print_job else None,
        print_job_printed_at=print_job.printed_at if print_job else None,
        print_job_failure_reason=print_job.failure_reason if print_job else None,
        device_code=device.device_code if device else None,
        device_status=device.status.value if device else None,
        device_printer_status=device.printer_status.value if device else None,
    )
