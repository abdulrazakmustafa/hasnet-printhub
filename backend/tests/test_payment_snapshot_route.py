import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.api.routes.payments import get_payment_by_provider_ref
from app.models.enums import PaymentStatus, PrinterStatus


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
    def __init__(self, payment=None, print_job=None, device=None):
        self._payment = payment
        self._print_job = print_job
        self._device = device

    def execute(self, _query):
        return _ExecuteResult(self._payment)

    def get(self, model, _key):
        name = model.__name__
        if name == "PrintJob":
            return self._print_job
        if name == "Device":
            return self._device
        return None


def test_payment_snapshot_rejects_empty_provider_ref() -> None:
    with pytest.raises(HTTPException) as exc:
        get_payment_by_provider_ref("   ", db=_FakeDB())

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "must not be empty" in exc.value.detail


def test_payment_snapshot_returns_404_when_not_found() -> None:
    with pytest.raises(HTTPException) as exc:
        get_payment_by_provider_ref("SN0001", db=_FakeDB(payment=None))

    assert exc.value.status_code == status.HTTP_404_NOT_FOUND
    assert "No payment found" in exc.value.detail


def test_payment_snapshot_returns_expected_payload() -> None:
    payment_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    job_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    device_id = uuid.UUID("44444444-4444-4444-4444-444444444444")

    payment = SimpleNamespace(
        id=payment_id,
        print_job_id=job_id,
        provider="snippe",
        provider_request_id="SN123",
        provider_transaction_ref="TRX123",
        status=PaymentStatus.confirmed,
        amount=500.0,
        currency="TZS",
        requested_at=None,
        confirmed_at=None,
        webhook_received_at=None,
        updated_at=None,
    )
    print_job = SimpleNamespace(
        id=job_id,
        device_id=device_id,
        status=SimpleNamespace(value="printed"),
        payment_status=SimpleNamespace(value="confirmed"),
        paid_at=None,
        printed_at=None,
        failure_reason=None,
    )
    device = SimpleNamespace(
        device_code="pi-kiosk-001",
        status=SimpleNamespace(value="online"),
        printer_status=PrinterStatus.ready,
    )

    result = get_payment_by_provider_ref("SN123", db=_FakeDB(payment=payment, print_job=print_job, device=device))

    assert result.payment_id == payment_id
    assert result.provider_request_id == "SN123"
    assert result.payment_status == "confirmed"
    assert result.print_job_status == "printed"
    assert result.device_code == "pi-kiosk-001"
    assert result.device_printer_status == "ready"
