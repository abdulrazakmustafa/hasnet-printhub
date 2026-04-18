import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.api.routes import payments as payments_routes
from app.models.enums import JobStatus, PaymentStatus
from app.schemas.payment import PaymentCreateRequest, PaymentCreateResponse


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
    def __init__(self, print_job=None, latest_payment=None):
        self._print_job = print_job
        self._latest_payment = latest_payment
        self.refreshed = False

    def get(self, model, _key):
        if model.__name__ == "PrintJob":
            return self._print_job
        return None

    def execute(self, _query):
        return _ExecuteResult(self._latest_payment)

    def refresh(self, _obj):
        self.refreshed = True


def _job(
    *,
    status: JobStatus = JobStatus.awaiting_payment,
    payment_status: PaymentStatus = PaymentStatus.pending,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        device_id=uuid.uuid4(),
        status=status,
        payment_status=payment_status,
    )


def _payment(status_value: PaymentStatus):
    return SimpleNamespace(
        status=status_value,
        provider_request_id="SN-TEST-001",
        requested_at=None,
        created_at=None,
    )


def test_retry_block_reason_blocks_pending_payment() -> None:
    reason = payments_routes._retry_block_reason_or_none(
        _job(),
        _payment(PaymentStatus.pending),
    )
    assert reason is not None
    assert "still pending after reconcile" in reason


def test_retry_safe_create_rejects_invalid_reconcile_limit() -> None:
    payload = PaymentCreateRequest(
        print_job_id=uuid.uuid4(),
        amount=1000,
        method="mpesa",
        msisdn="+255700111222",
    )
    with pytest.raises(HTTPException) as exc:
        payments_routes.retry_safe_create_payment(payload=payload, reconcile_limit=0, db=_FakeDB())
    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "reconcile_limit must be between 1 and 100" in exc.value.detail


def test_retry_safe_create_blocks_when_pending_remains(monkeypatch) -> None:
    payload = PaymentCreateRequest(
        print_job_id=uuid.uuid4(),
        amount=1000,
        method="mpesa",
        msisdn="+255700111222",
    )
    db = _FakeDB(print_job=_job(), latest_payment=_payment(PaymentStatus.pending))
    monkeypatch.setattr(payments_routes, "sync_pending_payments", lambda db, device_id, limit: 0)

    with pytest.raises(HTTPException) as exc:
        payments_routes.retry_safe_create_payment(payload=payload, reconcile_limit=25, db=db)

    assert exc.value.status_code == status.HTTP_409_CONFLICT
    assert "Do not retry yet." in exc.value.detail


def test_retry_safe_create_creates_new_payment_after_reconcile(monkeypatch) -> None:
    payload = PaymentCreateRequest(
        print_job_id=uuid.uuid4(),
        amount=1000,
        method="mpesa",
        msisdn="+255700111222",
    )
    db = _FakeDB(print_job=_job(), latest_payment=_payment(PaymentStatus.failed))
    calls: dict[str, int] = {"synced": 0}

    def _fake_sync(db, device_id, limit):
        del db, device_id
        calls["synced"] = limit
        return 3

    def _fake_create(payload, db):
        del db
        return PaymentCreateResponse(
            payment_id=uuid.uuid4(),
            status="pending",
            provider_request_id=f"SN-NEW-{payload.print_job_id.hex[:6]}",
            checkout_url=None,
        )

    monkeypatch.setattr(payments_routes, "sync_pending_payments", _fake_sync)
    monkeypatch.setattr(payments_routes, "create_provider_payment", _fake_create)

    result = payments_routes.retry_safe_create_payment(payload=payload, reconcile_limit=33, db=db)

    assert result.decision == "created_new_payment"
    assert result.reconcile_synced == 3
    assert result.payment.status == "pending"
    assert calls["synced"] == 33
    assert db.refreshed is True
