import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.api.routes.print_jobs import get_customer_receipt
from app.models.enums import ColorMode, JobStatus, PaymentStatus


class _ScalarResult:
    def __init__(self, item):
        self._item = item

    def first(self):
        return self._item


class _ExecuteResult:
    def __init__(self, item):
        self._item = item

    def scalars(self):
        return _ScalarResult(self._item)


class _FakeDB:
    def __init__(self, job=None, payment=None):
        self._job = job
        self._payment = payment

    def get(self, _model, _key):
        return self._job

    def execute(self, _query):
        return _ExecuteResult(self._payment)


def _build_job(payment_status: PaymentStatus, status_value: JobStatus):
    return SimpleNamespace(
        id=uuid.UUID("51515151-5151-5151-5151-515151515151"),
        payment_status=payment_status,
        status=status_value,
        payment_method=None,
        transaction_reference=None,
        total_cost=500.0,
        currency="TZS",
        pages=12,
        copies=1,
        color=ColorMode.bw,
        created_at=None,
        paid_at=None,
        printed_at=None,
        failure_reason=None,
    )


def _build_payment(status_value: PaymentStatus):
    return SimpleNamespace(
        id=uuid.UUID("61616161-6161-6161-6161-616161616161"),
        provider="snippe",
        provider_request_id="SN999",
        provider_transaction_ref="TRX-999",
        status=status_value,
        amount=500.0,
        currency="TZS",
        requested_at=None,
        confirmed_at=None,
        webhook_received_at=None,
        updated_at=None,
    )


def test_customer_receipt_rejects_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as exc:
        get_customer_receipt("bad-uuid", db=_FakeDB())

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Invalid job id" in exc.value.detail


def test_customer_receipt_returns_404_when_job_missing() -> None:
    with pytest.raises(HTTPException) as exc:
        get_customer_receipt(str(uuid.uuid4()), db=_FakeDB(job=None))

    assert exc.value.status_code == status.HTTP_404_NOT_FOUND
    assert "Print job not found" in exc.value.detail


def test_customer_receipt_completed_shape() -> None:
    job = _build_job(PaymentStatus.confirmed, JobStatus.printed)
    payment = _build_payment(PaymentStatus.confirmed)
    result = get_customer_receipt(str(job.id), db=_FakeDB(job=job, payment=payment))

    assert result.contract_version == "customer-receipt-v1"
    assert result.stage == "completed"
    assert result.headline == "Payment Success and Print Completed"
    assert result.receipt is not None
    assert result.receipt.provider_request_id == "SN999"
    assert len(result.timeline) == 5


def test_customer_receipt_payment_pending_shape() -> None:
    job = _build_job(PaymentStatus.pending, JobStatus.awaiting_payment)
    payment = _build_payment(PaymentStatus.pending)
    result = get_customer_receipt(str(job.id), db=_FakeDB(job=job, payment=payment))

    assert result.stage == "payment_pending"
    assert result.headline == "Payment Pending Confirmation"
