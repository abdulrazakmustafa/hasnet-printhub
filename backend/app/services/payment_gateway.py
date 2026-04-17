from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import JobStatus, PaymentMethod, PaymentStatus
from app.schemas.payment import PaymentCreateRequest, PaymentCreateResponse

if TYPE_CHECKING:
    from app.models.payment import Payment

_SNIPPE_TIMEOUT_SECONDS = 20
_MIXX_TIMEOUT_SECONDS = 20
_WEBHOOK_MAX_SKEW_SECONDS = 300


def _normalize_msisdn(msisdn: str) -> str:
    normalized = msisdn.strip().replace(" ", "").replace("-", "")
    if normalized.startswith("00"):
        normalized = "+" + normalized[2:]

    digits = normalized[1:] if normalized.startswith("+") else normalized
    if not digits.isdigit() or len(digits) < 10 or len(digits) > 15:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid MSISDN format. Use 10 to 15 digits (optional leading +).",
        )

    return normalized


def _map_method(method: str) -> PaymentMethod:
    normalized = method.strip().lower()
    try:
        return PaymentMethod(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported payment method '{method}'.",
        ) from exc


def _map_snippe_status(raw_status: str | None) -> PaymentStatus:
    normalized = (raw_status or "").strip().lower()
    if normalized in {"completed", "confirmed", "paid", "success", "successful"}:
        return PaymentStatus.confirmed
    if normalized in {"failed", "declined", "cancelled", "canceled", "voided"}:
        return PaymentStatus.failed
    if normalized in {"expired", "timeout", "timed_out"}:
        return PaymentStatus.expired
    if normalized in {"pending", "initiated", "processing", "queued"}:
        return PaymentStatus.pending
    return PaymentStatus.pending


def _map_mixx_status(raw_status: str | bool | None) -> PaymentStatus:
    if isinstance(raw_status, bool):
        return PaymentStatus.confirmed if raw_status else PaymentStatus.failed

    normalized = (str(raw_status or "")).strip().lower()
    if normalized in {"true", "success", "successful", "completed", "confirmed", "paid"}:
        return PaymentStatus.confirmed
    if normalized in {"false", "failed", "declined", "cancelled", "canceled", "error"}:
        return PaymentStatus.failed
    return PaymentStatus.pending


def _response_status_is_success(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() == "true"


def _snippe_config_or_500() -> tuple[str, str]:
    base_url = settings.snippe_base_url.strip().rstrip("/")
    api_key = settings.snippe_api_key.strip()
    if not base_url or not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Snippe credentials are not configured.",
        )
    return base_url, api_key


def _mixx_config_or_500() -> tuple[str, str, str, str, str]:
    base_url = settings.mixx_base_url.strip().rstrip("/")
    payment_path = settings.mixx_payment_path.strip()
    api_key = settings.mixx_api_key.strip()
    user_id = settings.mixx_user_id.strip()
    biller_msisdn = settings.mixx_biller_msisdn.strip()

    if not base_url or not api_key or not user_id or not biller_msisdn:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Mixx credentials are not configured. Required: "
                "MIXX_BASE_URL, MIXX_API_KEY, MIXX_USER_ID, MIXX_BILLER_MSISDN."
            ),
        )
    return base_url, payment_path, api_key, user_id, _normalize_msisdn(biller_msisdn)


def _active_payment_provider() -> str:
    provider = settings.payment_provider.strip().lower()
    if provider not in {"snippe", "mixx"}:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unsupported PAYMENT_PROVIDER. Use 'snippe' or 'mixx'.",
        )
    return provider


def _build_idempotency_key(print_job_id: uuid.UUID) -> str:
    return f"ph_{print_job_id.hex[:27]}"


def _build_mixx_reference_id(print_job_id: uuid.UUID) -> str:
    now_ms = int(time.time() * 1000)
    return f"HPH{now_ms}{print_job_id.hex[:8]}".upper()


def _parse_json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        parsed = response.json()
    except json.JSONDecodeError:
        return {"raw": response.text}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


def _validate_payment_request_state(
    payload: PaymentCreateRequest,
    print_job: "PrintJob",
    latest_pending_payment: "Payment | None",
) -> None:
    amount = round(payload.amount, 2)
    expected_amount = round(float(print_job.total_cost), 2)
    if abs(amount - expected_amount) > 0.01:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Payment amount must match job total ({expected_amount:.2f} {print_job.currency}).",
        )

    if print_job.status in {JobStatus.paid, JobStatus.queued, JobStatus.dispatched, JobStatus.printing, JobStatus.printed}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment cannot be created because this job is already paid or in print workflow.",
        )

    if print_job.payment_status == PaymentStatus.confirmed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment already confirmed for this print job.",
        )

    if latest_pending_payment is not None:
        pending_ref = latest_pending_payment.provider_request_id or "unknown"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A pending payment already exists for this print job "
                f"(provider_request_id={pending_ref}). Reconcile before creating another."
            ),
        )


def _validate_payment_request_context(payload: PaymentCreateRequest, db: Session) -> None:
    from app.models.payment import Payment
    from app.models.print_job import PrintJob

    print_job = db.get(PrintJob, payload.print_job_id)
    if print_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print job not found.")

    latest_pending_payment = (
        db.execute(
            select(Payment)
            .where(
                Payment.print_job_id == payload.print_job_id,
                Payment.status == PaymentStatus.pending,
            )
            .order_by(Payment.requested_at.desc(), Payment.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    _validate_payment_request_state(payload=payload, print_job=print_job, latest_pending_payment=latest_pending_payment)


def create_payment(payload: PaymentCreateRequest, db: Session) -> PaymentCreateResponse:
    _validate_payment_request_context(payload=payload, db=db)
    provider = _active_payment_provider()
    if provider == "mixx":
        return create_mixx_payment(payload=payload, db=db)
    return create_snippe_payment(payload=payload, db=db)


def create_mixx_payment(payload: PaymentCreateRequest, db: Session) -> PaymentCreateResponse:
    from app.models.log import LogEntry
    from app.models.payment import Payment
    from app.models.print_job import PrintJob

    base_url, payment_path, api_key, user_id, biller_msisdn = _mixx_config_or_500()
    method = _map_method(payload.method)

    print_job = db.get(PrintJob, payload.print_job_id)
    if print_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print job not found.")

    amount = round(payload.amount, 2)
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payment amount must be positive.",
        )

    reference_id = _build_mixx_reference_id(payload.print_job_id)
    request_amount = int(round(amount))
    body: dict[str, Any] = {
        "CustomerMSISDN": _normalize_msisdn(payload.msisdn),
        "BillerMSISDN": biller_msisdn,
        "Amount": request_amount,
        "ReferenceID": reference_id,
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-API-Key": api_key,
        "X-User-Id": user_id,
    }
    endpoint = f"{base_url}/{payment_path.lstrip('/')}" if payment_path else base_url

    try:
        with httpx.Client(timeout=_MIXX_TIMEOUT_SECONDS, trust_env=False) as client:
            response = client.post(endpoint, headers=headers, json=body)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to reach Mixx gateway: {exc}",
        ) from exc

    response_payload = _parse_json_response(response)
    if response.is_error:
        message = str(
            response_payload.get("ResponseDescription")
            or response_payload.get("detail")
            or response_payload.get("Message")
            or "Mixx request failed."
        )
        http_status = response.status_code if response.status_code < 500 else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=http_status, detail=message)

    response_ok = _response_status_is_success(response_payload.get("ResponseStatus"))
    if not response_ok:
        detail = str(
            response_payload.get("ResponseDescription")
            or response_payload.get("Message")
            or "Mixx rejected the push-payment request."
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)

    payment = Payment(
        print_job_id=print_job.id,
        provider="mixx",
        method=method,
        amount=amount,
        currency=print_job.currency,
        status=PaymentStatus.pending,
        provider_request_id=reference_id,
        provider_transaction_ref=None,
        provider_payload=response_payload,
        confirmed_at=None,
    )
    db.add(payment)

    print_job.payment_method = method
    print_job.payment_status = PaymentStatus.pending
    print_job.status = JobStatus.awaiting_payment

    db.add(
        LogEntry(
            device_id=print_job.device_id,
            print_job_id=print_job.id,
            payment_id=payment.id,
            level="info",
            event_type="payment.create.mixx",
            message="Payment push request created via Mixx.",
            payload={
                "provider_request_id": reference_id,
                "response_code": response_payload.get("ResponseCode"),
                "response_description": response_payload.get("ResponseDescription"),
            },
        )
    )

    db.commit()
    db.refresh(payment)

    return PaymentCreateResponse(
        payment_id=payment.id,
        status=payment.status.value,
        provider_request_id=reference_id,
        checkout_url=None,
    )


def create_snippe_payment(payload: PaymentCreateRequest, db: Session) -> PaymentCreateResponse:
    from app.models.log import LogEntry
    from app.models.payment import Payment
    from app.models.print_job import PrintJob

    base_url, api_key = _snippe_config_or_500()
    method = _map_method(payload.method)

    print_job = db.get(PrintJob, payload.print_job_id)
    if print_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print job not found.")

    amount = round(payload.amount, 2)
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payment amount must be positive.",
        )

    body: dict[str, Any] = {
        "payment_type": "mobile",
        "details": {
            "amount": int(round(amount)),
            "currency": print_job.currency,
        },
        "phone_number": _normalize_msisdn(payload.msisdn),
        "customer": {
            "firstname": payload.customer_first_name,
            "lastname": payload.customer_last_name,
            "email": payload.customer_email,
        },
        "metadata": {
            "print_job_id": str(payload.print_job_id),
            "method": method.value,
        },
    }
    webhook_url = settings.snippe_webhook_url.strip()
    if webhook_url:
        body["webhook_url"] = webhook_url

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Idempotency-Key": _build_idempotency_key(payload.print_job_id),
    }

    try:
        with httpx.Client(timeout=_SNIPPE_TIMEOUT_SECONDS, trust_env=False) as client:
            response = client.post(
                f"{base_url}/v1/payments",
                headers=headers,
                json=body,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to reach Snippe: {exc}",
        ) from exc

    response_payload = _parse_json_response(response)
    if response.is_error:
        message = str(response_payload.get("message") or response_payload.get("error") or "Snippe request failed.")
        http_status = response.status_code if response.status_code < 500 else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=http_status, detail=message)

    snippe_data = response_payload.get("data") if isinstance(response_payload.get("data"), dict) else {}
    provider_request_id = str(
        snippe_data.get("reference")
        or snippe_data.get("id")
        or f"snippe_{uuid.uuid4().hex[:16]}"
    )
    provider_transaction_ref = snippe_data.get("external_reference")
    provider_status = _map_snippe_status(snippe_data.get("status"))

    payment = Payment(
        print_job_id=print_job.id,
        provider="snippe",
        method=method,
        amount=amount,
        currency=print_job.currency,
        status=provider_status,
        provider_request_id=provider_request_id,
        provider_transaction_ref=provider_transaction_ref,
        provider_payload=response_payload,
        confirmed_at=datetime.now(timezone.utc) if provider_status == PaymentStatus.confirmed else None,
    )
    db.add(payment)

    print_job.payment_method = method
    print_job.payment_status = provider_status
    if provider_transaction_ref:
        print_job.transaction_reference = provider_transaction_ref

    if provider_status == PaymentStatus.confirmed:
        print_job.status = JobStatus.paid
        print_job.paid_at = datetime.now(timezone.utc)
    elif provider_status == PaymentStatus.failed:
        print_job.status = JobStatus.failed
        print_job.failure_reason = "Payment failed at Snippe create call."
    elif provider_status == PaymentStatus.expired:
        print_job.status = JobStatus.expired
        print_job.failure_reason = "Payment expired at Snippe create call."
    else:
        print_job.status = JobStatus.awaiting_payment

    db.add(
        LogEntry(
            device_id=print_job.device_id,
            print_job_id=print_job.id,
            payment_id=payment.id,
            level="info",
            event_type="payment.create.snippe",
            message="Payment created via Snippe.",
            payload={
                "provider_request_id": provider_request_id,
                "provider_status": snippe_data.get("status"),
            },
        )
    )

    db.commit()
    db.refresh(payment)

    return PaymentCreateResponse(
        payment_id=payment.id,
        status=payment.status.value,
        provider_request_id=provider_request_id,
        checkout_url=snippe_data.get("payment_url"),
    )


def _verify_snippe_webhook_signature(raw_body: bytes, headers: Mapping[str, str]) -> None:
    webhook_secret = settings.snippe_webhook_secret.strip()
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Snippe webhook secret is not configured.",
        )

    timestamp = headers.get("X-Webhook-Timestamp")
    signature = headers.get("X-Webhook-Signature")
    if not timestamp or not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook signature headers.")

    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook timestamp.") from exc

    if abs(int(time.time()) - timestamp_value) > _WEBHOOK_MAX_SKEW_SECONDS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook timestamp outside allowed window.")

    expected = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook signature mismatch.")


def _parse_webhook_payload(raw_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook JSON payload.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload shape.")
    return payload


def _payload_value(payload: Mapping[str, Any], *keys: str) -> Any:
    lowered = {str(k).lower(): v for k, v in payload.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def handle_mixx_webhook(raw_body: bytes, headers: Mapping[str, str], db: Session) -> dict[str, object]:
    from app.models.log import LogEntry
    from app.models.payment import Payment
    from app.models.print_job import PrintJob

    del headers  # Mixx document does not define webhook signature headers.
    payload = _parse_webhook_payload(raw_body)

    reference_id = str(
        _payload_value(payload, "ReferenceID", "referenceID", "reference_id", "referenceId") or ""
    ).strip()
    if not reference_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing ReferenceID in Mixx callback.")

    payment = (
        db.execute(
            select(Payment)
            .where(Payment.provider == "mixx", Payment.provider_request_id == reference_id)
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )

    if payment is None:
        db.add(
            LogEntry(
                device_id=None,
                print_job_id=None,
                payment_id=None,
                level="warning",
                event_type="payment.webhook.mixx.unmatched",
                message="Received Mixx callback for unknown reference ID.",
                payload={"reference_id": reference_id, "raw": payload},
            )
        )
        db.commit()
        return {
            "success": False,
            "responseCode": "BILLER-18-3020-E",
            "transactionStatus": "false",
            "errorDescription": "Unknown reference ID",
            "referenceID": reference_id,
        }

    mapped_status = _map_mixx_status(_payload_value(payload, "Status", "status", "transactionStatus"))
    provider_transaction_ref = str(
        _payload_value(payload, "MFSTransactionID", "mfsTransactionID", "mfs_transaction_id") or ""
    ).strip()

    payment.status = mapped_status
    payment.webhook_received_at = datetime.now(timezone.utc)
    payment.provider_payload = payload
    if provider_transaction_ref:
        payment.provider_transaction_ref = provider_transaction_ref
    if mapped_status == PaymentStatus.confirmed and payment.confirmed_at is None:
        payment.confirmed_at = datetime.now(timezone.utc)

    print_job = db.get(PrintJob, payment.print_job_id)
    if print_job is not None:
        print_job.payment_status = mapped_status
        if provider_transaction_ref:
            print_job.transaction_reference = provider_transaction_ref

        if mapped_status == PaymentStatus.confirmed:
            print_job.status = JobStatus.paid
            if print_job.paid_at is None:
                print_job.paid_at = datetime.now(timezone.utc)
        elif mapped_status == PaymentStatus.failed:
            print_job.status = JobStatus.failed
            print_job.failure_reason = (
                str(_payload_value(payload, "Description", "description") or "Payment failed via Mixx callback.")
            )
        elif mapped_status == PaymentStatus.expired:
            print_job.status = JobStatus.expired
            print_job.failure_reason = "Payment expired via Mixx callback."
        else:
            print_job.status = JobStatus.awaiting_payment

        db.add(
            LogEntry(
                device_id=print_job.device_id,
                print_job_id=print_job.id,
                payment_id=payment.id,
                level="info",
                event_type="payment.webhook.mixx",
                message="Mixx callback processed.",
                payload={
                    "reference_id": reference_id,
                    "mapped_status": mapped_status.value,
                    "provider_transaction_ref": provider_transaction_ref or None,
                    "description": _payload_value(payload, "Description", "description"),
                },
            )
        )
    else:
        db.add(
            LogEntry(
                device_id=None,
                print_job_id=None,
                payment_id=payment.id,
                level="warning",
                event_type="payment.webhook.mixx.orphan_payment",
                message="Mixx callback matched a payment without a print job.",
                payload={"reference_id": reference_id},
            )
        )

    db.commit()
    return {
        "success": True,
        "responseCode": "BILLER-18-0000-S",
        "transactionStatus": "true" if mapped_status == PaymentStatus.confirmed else "false",
        "errorDescription": "Callback successful",
        "referenceID": reference_id,
    }


def handle_snippe_webhook(raw_body: bytes, headers: Mapping[str, str], db: Session) -> None:
    from app.models.log import LogEntry
    from app.models.payment import Payment
    from app.models.print_job import PrintJob

    _verify_snippe_webhook_signature(raw_body=raw_body, headers=headers)
    payload = _parse_webhook_payload(raw_body)

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    provider_request_id = str(data.get("reference") or payload.get("reference") or "").strip()
    if not provider_request_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Snippe reference in webhook payload.")

    payment = (
        db.execute(
            select(Payment)
            .where(Payment.provider_request_id == provider_request_id)
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if payment is None:
        db.add(
            LogEntry(
                device_id=None,
                print_job_id=None,
                payment_id=None,
                level="warning",
                event_type="payment.webhook.snippe.unmatched",
                message="Received Snippe webhook for unknown provider reference.",
                payload={"provider_request_id": provider_request_id, "raw": payload},
            )
        )
        db.commit()
        return

    provider_transaction_ref = data.get("external_reference") or payload.get("external_reference")
    provider_status = _map_snippe_status(data.get("status") or payload.get("status"))

    payment.status = provider_status
    payment.webhook_received_at = datetime.now(timezone.utc)
    payment.provider_payload = payload
    if provider_transaction_ref:
        payment.provider_transaction_ref = provider_transaction_ref
    if provider_status == PaymentStatus.confirmed and payment.confirmed_at is None:
        payment.confirmed_at = datetime.now(timezone.utc)

    print_job = db.get(PrintJob, payment.print_job_id)
    if print_job is not None:
        print_job.payment_status = provider_status
        if provider_transaction_ref:
            print_job.transaction_reference = provider_transaction_ref

        if provider_status == PaymentStatus.confirmed:
            print_job.status = JobStatus.paid
            if print_job.paid_at is None:
                print_job.paid_at = datetime.now(timezone.utc)
        elif provider_status == PaymentStatus.failed:
            print_job.status = JobStatus.failed
            print_job.failure_reason = "Payment failed via Snippe webhook."
        elif provider_status == PaymentStatus.expired:
            print_job.status = JobStatus.expired
            print_job.failure_reason = "Payment expired via Snippe webhook."
        else:
            print_job.status = JobStatus.awaiting_payment

        db.add(
            LogEntry(
                device_id=print_job.device_id,
                print_job_id=print_job.id,
                payment_id=payment.id,
                level="info",
                event_type="payment.webhook.snippe",
                message="Snippe webhook processed.",
                payload={
                    "provider_request_id": provider_request_id,
                    "provider_status": data.get("status") or payload.get("status"),
                    "mapped_status": provider_status.value,
                },
            )
        )
    else:
        db.add(
            LogEntry(
                device_id=None,
                print_job_id=None,
                payment_id=payment.id,
                level="warning",
                event_type="payment.webhook.snippe.orphan_payment",
                message="Snippe webhook matched a payment without a print job.",
                payload={"provider_request_id": provider_request_id},
            )
        )

    db.commit()


def sync_pending_snippe_payments(db: Session, *, device_id: uuid.UUID | None = None, limit: int = 10) -> int:
    """Best-effort sync for pending Snippe payments when webhook is unavailable.

    This keeps prototype environments working even if SNIPPE_WEBHOOK_URL is not publicly reachable.
    """
    from app.models.log import LogEntry
    from app.models.payment import Payment
    from app.models.print_job import PrintJob

    base_url, api_key = _snippe_config_or_500()

    query = (
        select(Payment)
        .where(
            Payment.provider == "snippe",
            Payment.status == PaymentStatus.pending,
            Payment.provider_request_id.is_not(None),
        )
        .order_by(Payment.created_at.asc())
        .limit(max(1, min(limit, 50)))
    )
    candidates = db.execute(query).scalars().all()
    if not candidates:
        return 0

    if device_id is not None:
        filtered: list[Payment] = []
        for payment in candidates:
            print_job = db.get(PrintJob, payment.print_job_id)
            if print_job and print_job.device_id == device_id:
                filtered.append(payment)
        candidates = filtered
        if not candidates:
            return 0

    synced = 0
    with httpx.Client(timeout=_SNIPPE_TIMEOUT_SECONDS, trust_env=False) as client:
        for payment in candidates:
            provider_request_id = (payment.provider_request_id or "").strip()
            if not provider_request_id:
                continue

            try:
                response = client.get(
                    f"{base_url}/v1/payments/{provider_request_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
            except httpx.RequestError:
                continue
            except httpx.HTTPStatusError:
                continue

            response_payload = _parse_json_response(response)
            data = response_payload.get("data") if isinstance(response_payload.get("data"), dict) else {}
            mapped_status = _map_snippe_status(data.get("status"))

            payment.webhook_received_at = datetime.now(timezone.utc)
            payment.provider_payload = response_payload

            provider_transaction_ref = data.get("external_reference")
            if provider_transaction_ref:
                payment.provider_transaction_ref = provider_transaction_ref

            if mapped_status == payment.status:
                continue

            payment.status = mapped_status
            if mapped_status == PaymentStatus.confirmed and payment.confirmed_at is None:
                payment.confirmed_at = datetime.now(timezone.utc)

            print_job = db.get(PrintJob, payment.print_job_id)
            if print_job is not None:
                print_job.payment_status = mapped_status
                if provider_transaction_ref:
                    print_job.transaction_reference = provider_transaction_ref

                if mapped_status == PaymentStatus.confirmed:
                    print_job.status = JobStatus.paid
                    if print_job.paid_at is None:
                        print_job.paid_at = datetime.now(timezone.utc)
                elif mapped_status == PaymentStatus.failed:
                    print_job.status = JobStatus.failed
                    print_job.failure_reason = "Payment failed via Snippe status sync."
                elif mapped_status == PaymentStatus.expired:
                    print_job.status = JobStatus.expired
                    print_job.failure_reason = "Payment expired via Snippe status sync."
                else:
                    print_job.status = JobStatus.awaiting_payment

                db.add(
                    LogEntry(
                        device_id=print_job.device_id,
                        print_job_id=print_job.id,
                        payment_id=payment.id,
                        level="info",
                        event_type="payment.sync.snippe",
                        message="Snippe payment status synced from provider API.",
                        payload={
                            "provider_request_id": provider_request_id,
                            "provider_status": data.get("status"),
                            "mapped_status": mapped_status.value,
                        },
                    )
                )
            else:
                db.add(
                    LogEntry(
                        device_id=None,
                        print_job_id=None,
                        payment_id=payment.id,
                        level="warning",
                        event_type="payment.sync.snippe.orphan_payment",
                        message="Synced Snippe payment has no matching print job.",
                        payload={"provider_request_id": provider_request_id},
                    )
                )
            synced += 1

    if synced:
        db.commit()
    return synced


def sync_pending_payments(db: Session, *, device_id: uuid.UUID | None = None, limit: int = 10) -> int:
    """Sync pending payments for the active provider when a pull API is available."""
    provider = _active_payment_provider()
    if provider == "snippe":
        return sync_pending_snippe_payments(db, device_id=device_id, limit=limit)
    return 0
