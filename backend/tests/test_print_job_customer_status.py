import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.api.routes.print_jobs import get_customer_job_status
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
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
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


def test_customer_status_rejects_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as exc:
        get_customer_job_status("not-a-uuid", db=_FakeDB())

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Invalid job id" in exc.value.detail


def test_customer_status_returns_404_when_job_missing() -> None:
    with pytest.raises(HTTPException) as exc:
        get_customer_job_status(str(uuid.uuid4()), db=_FakeDB(job=None))

    assert exc.value.status_code == status.HTTP_404_NOT_FOUND
    assert "Print job not found" in exc.value.detail


def test_customer_status_returns_pending_stage() -> None:
    job = _build_job(PaymentStatus.pending, JobStatus.awaiting_payment)
    payment = SimpleNamespace(provider="snippe", provider_request_id="SN123", provider_transaction_ref=None)
    result = get_customer_job_status(str(job.id), db=_FakeDB(job=job, payment=payment))

    assert result.stage == "payment_pending"
    assert result.payment_status == "pending"
    assert result.provider_request_id == "SN123"


def test_customer_status_returns_completed_stage() -> None:
    job = _build_job(PaymentStatus.confirmed, JobStatus.printed)
    payment = SimpleNamespace(provider="snippe", provider_request_id="SN123", provider_transaction_ref="TRX9")
    result = get_customer_job_status(str(job.id), db=_FakeDB(job=job, payment=payment))

    assert result.stage == "completed"
    assert result.job_status == "printed"
    assert result.provider_transaction_ref == "TRX9"


def test_customer_status_returns_payment_failed_stage() -> None:
    job = _build_job(PaymentStatus.failed, JobStatus.failed)
    result = get_customer_job_status(str(job.id), db=_FakeDB(job=job, payment=None))

    assert result.stage == "payment_failed"
    assert result.payment_status == "failed"
