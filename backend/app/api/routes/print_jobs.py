import uuid
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
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
    PrintJobUploadResponse,
)
from app.services.pricing import compute_total_cost
from app.services.upload_storage import (
    UPLOADS_DIR,
    UPLOAD_META_SUFFIX,
    cleanup_stale_upload_artifacts,
    upload_file_path,
    upload_meta_path,
)

router = APIRouter()
_ALLOWED_UPLOAD_TYPES = {"application/pdf", "application/x-pdf"}


def _validate_upload_filename_or_422(file_name: str) -> str:
    normalized = (file_name or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Uploaded file name is required.")
    if "/" in normalized or "\\" in normalized or ".." in normalized:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid uploaded file name.")
    if len(normalized) > 255:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file name must be 255 characters or fewer.",
        )
    if not normalized.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only .pdf files are allowed.")
    return normalized


def _build_upload_storage_key(request: Request, upload_id: str) -> str:
    api_prefix = settings.api_v1_prefix.rstrip("/")
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}{api_prefix}/test-assets/uploads/{upload_id}.pdf"


def _load_upload_meta_or_422(upload_id: str) -> tuple[Path, dict]:
    try:
        parsed = uuid.UUID(upload_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="upload_id must be a valid UUID.") from exc

    normalized_upload_id = str(parsed)
    file_path = upload_file_path(normalized_upload_id)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Referenced upload_id file was not found.")

    meta_path = upload_meta_path(normalized_upload_id)
    if not meta_path.exists() or not meta_path.is_file():
        return file_path, {}

    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    return file_path, metadata


def _detect_pdf_page_count_or_422(pdf_bytes: bytes) -> int:
    page_hits = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
    page_count = len(page_hits)
    if page_count < 1:
        count_hits = re.findall(rb"/Count\s+(\d+)", pdf_bytes)
        parsed_counts = []
        for raw in count_hits:
            try:
                parsed_counts.append(int(raw))
            except ValueError:
                continue
        if parsed_counts:
            page_count = max(parsed_counts)

    if page_count < 1 or page_count > 2000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF page count is outside supported range (1-2000).",
        )
    return page_count


def _resolve_upload_page_count_or_422(upload_meta: dict, upload_file_path: Path) -> int:
    raw_page_count = upload_meta.get("page_count")
    try:
        parsed = int(raw_page_count)
        if 1 <= parsed <= 2000:
            return parsed
    except (TypeError, ValueError):
        pass

    return _detect_pdf_page_count_or_422(upload_file_path.read_bytes())


def _resolve_selected_pages_or_422(
    *,
    total_pages: int,
    page_selection: str,
    range_start_page: int | None,
    range_end_page: int | None,
) -> int:
    normalized_selection = (page_selection or "all").strip().lower()
    if normalized_selection == "all":
        return total_pages

    if normalized_selection != "range":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="page_selection must be either 'all' or 'range'.",
        )

    if range_start_page is None or range_end_page is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Both range_start_page and range_end_page are required when page_selection is 'range'.",
        )
    if range_start_page < 1 or range_end_page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Custom page range values must be >= 1.",
        )
    if range_start_page > range_end_page:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="range_start_page must be less than or equal to range_end_page.",
        )
    if range_end_page > total_pages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Custom page range exceeds document length ({total_pages} pages).",
        )
    return (range_end_page - range_start_page) + 1


@router.post("/upload", response_model=PrintJobUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_print_job_pdf(request: Request, file: UploadFile = File(...)) -> PrintJobUploadResponse:
    cleanup_stale_upload_artifacts(max_age_hours=int(getattr(settings, "upload_artifact_ttl_hours", 24)))

    file_name = _validate_upload_filename_or_422(file.filename or "")
    content_type = (file.content_type or "").lower().strip()
    if content_type and content_type not in _ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only PDF uploads are supported.")

    max_bytes = max(1, settings.upload_max_mb) * 1024 * 1024
    payload = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        payload.extend(chunk)
        if len(payload) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Uploaded file exceeds {settings.upload_max_mb} MB limit.",
            )
    await file.close()

    if not payload:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Uploaded file is empty.")
    payload_bytes = bytes(payload)
    if not payload_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Uploaded content is not a PDF.")
    page_count = _detect_pdf_page_count_or_422(payload_bytes)

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    upload_id = str(uuid.uuid4())
    stored_name = f"{upload_id}.pdf"
    stored_path = UPLOADS_DIR / stored_name
    stored_path.write_bytes(payload_bytes)
    sha256 = hashlib.sha256(payload_bytes).hexdigest()
    metadata = {
        "upload_id": upload_id,
        "file_name": file_name,
        "file_size_bytes": len(payload),
        "content_type": "application/pdf",
        "sha256": sha256,
        "page_count": page_count,
        "stored_name": stored_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    upload_meta_path(upload_id).write_text(json.dumps(metadata), encoding="utf-8")

    storage_key = _build_upload_storage_key(request, upload_id)

    return PrintJobUploadResponse(
        upload_id=upload_id,
        storage_key=storage_key,
        file_name=file_name,
        file_size_bytes=len(payload),
        content_type="application/pdf",
        sha256=sha256,
        page_count=page_count,
    )


@router.post("", response_model=PrintJobCreateResponse)
def create_quote(payload: PrintJobCreateRequest, request: Request, db: Session = Depends(get_db)) -> PrintJobCreateResponse:
    try:
        color_mode = ColorMode(payload.color)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported color mode '{payload.color}'.",
        ) from exc
    price_per_page = payload.color_price_per_page if color_mode == ColorMode.color else payload.bw_price_per_page
    effective_pages = payload.pages

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
    file_sha256 = "0" * 64
    file_size_bytes = 1
    normalized_upload_id = (payload.upload_id or "").strip()
    if normalized_upload_id:
        upload_file_path, upload_meta = _load_upload_meta_or_422(normalized_upload_id)
        effective_pages = _resolve_upload_page_count_or_422(upload_meta, upload_file_path)
        if not (payload.storage_key or "").strip():
            storage_key = _build_upload_storage_key(request, normalized_upload_id)
        if (payload.original_file_name or "").strip().lower() == "pending-upload.pdf":
            upload_file_name = str(upload_meta.get("file_name") or "").strip()
            if upload_file_name:
                original_file_name = upload_file_name
        try:
            file_size_bytes = int(upload_meta.get("file_size_bytes") or upload_file_path.stat().st_size)
        except (TypeError, ValueError):
            file_size_bytes = int(upload_file_path.stat().st_size)
        sha_value = str(upload_meta.get("sha256") or "").strip().lower()
        if len(sha_value) == 64 and all(ch in "0123456789abcdef" for ch in sha_value):
            file_sha256 = sha_value
        else:
            file_sha256 = hashlib.sha256(upload_file_path.read_bytes()).hexdigest()

    selected_pages = _resolve_selected_pages_or_422(
        total_pages=effective_pages,
        page_selection=payload.page_selection,
        range_start_page=payload.range_start_page,
        range_end_page=payload.range_end_page,
    )

    total = compute_total_cost(
        pages=selected_pages,
        copies=payload.copies,
        color=payload.color,
        bw_price_per_page=payload.bw_price_per_page,
        color_price_per_page=payload.color_price_per_page,
    )

    job = PrintJob(
        device_id=device.id,
        original_file_name=original_file_name,
        storage_key=storage_key,
        file_sha256=file_sha256,
        file_size_bytes=file_size_bytes,
        pages=selected_pages,
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


def _is_pending_provider_delay(job: PrintJob, payment: Payment | None) -> bool:
    if job.payment_status != PaymentStatus.pending:
        return False

    pending_since = payment.requested_at if payment and payment.requested_at else job.created_at
    if pending_since is None:
        return False

    if pending_since.tzinfo is None:
        pending_since = pending_since.replace(tzinfo=timezone.utc)

    escalation_window = timedelta(minutes=settings.customer_pending_escalation_minutes)
    return datetime.now(timezone.utc) - pending_since >= escalation_window


def _resolve_customer_stage(job: PrintJob, payment: Payment | None) -> tuple[str, str, str]:
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
        if _is_pending_provider_delay(job, payment):
            stage = "provider_delay_escalated"
            message = "Payment confirmation is delayed at provider side."
            next_action = "Operator should reconcile and verify provider reference status."
        else:
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


def _build_customer_timeline(job: PrintJob, payment: Payment | None, stage: str) -> list[CustomerTimelineEvent]:
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
    elif stage == "provider_delay_escalated":
        confirmation_state = "current"
        confirmation_detail = "Provider confirmation delayed. Operator reconciliation in progress."
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

    stage, message, next_action = _resolve_customer_stage(job, latest_payment)
    timeline = _build_customer_timeline(job, latest_payment, stage)
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

    stage, message, next_action = _resolve_customer_stage(job, latest_payment)
    timeline = _build_customer_timeline(job, latest_payment, stage)
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
    elif stage == "provider_delay_escalated":
        headline = "Provider Delay - Verification In Progress"

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
