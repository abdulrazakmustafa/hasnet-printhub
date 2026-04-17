import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.models.enums import JobStatus, PaymentMethod, PaymentStatus
from app.services.payment_gateway import (
    _build_idempotency_key,
    _build_mixx_reference_id,
    _map_method,
    _map_mixx_status,
    _map_snippe_status,
    _normalize_msisdn,
    _response_status_is_success,
    _validate_payment_request_state,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("completed", PaymentStatus.confirmed),
        ("successful", PaymentStatus.confirmed),
        ("failed", PaymentStatus.failed),
        ("cancelled", PaymentStatus.failed),
        ("expired", PaymentStatus.expired),
        ("pending", PaymentStatus.pending),
        ("something-unknown", PaymentStatus.pending),
        (None, PaymentStatus.pending),
    ],
)
def test_map_snippe_status(raw: str | None, expected: PaymentStatus) -> None:
    assert _map_snippe_status(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (True, PaymentStatus.confirmed),
        (False, PaymentStatus.failed),
        ("true", PaymentStatus.confirmed),
        ("success", PaymentStatus.confirmed),
        ("false", PaymentStatus.failed),
        ("declined", PaymentStatus.failed),
        ("unknown", PaymentStatus.pending),
        (None, PaymentStatus.pending),
    ],
)
def test_map_mixx_status(raw: str | bool | None, expected: PaymentStatus) -> None:
    assert _map_mixx_status(raw) == expected


def test_map_method_normalizes_value() -> None:
    assert _map_method("  TIGO  ") == PaymentMethod.tigo


def test_map_method_rejects_unsupported_method() -> None:
    with pytest.raises(HTTPException) as exc:
        _map_method("paypal")

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Unsupported payment method" in exc.value.detail


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("TRUE", True),
        (" false ", False),
        (None, False),
    ],
)
def test_response_status_is_success(raw: object, expected: bool) -> None:
    assert _response_status_is_success(raw) is expected


def test_build_idempotency_key_shape() -> None:
    key = _build_idempotency_key(uuid.UUID("12345678-1234-5678-1234-567812345678"))
    assert key.startswith("ph_")
    assert len(key) == 30


def test_build_mixx_reference_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.payment_gateway.time.time", lambda: 1710000000.123)
    ref = _build_mixx_reference_id(uuid.UUID("12345678-1234-5678-1234-567812345678"))
    assert ref.startswith("HPH1710000000123")
    assert ref.endswith("12345678")


def _payment_payload(amount: float = 500.0):
    return SimpleNamespace(amount=amount)


def _print_job(
    total_cost: float = 500.0,
    currency: str = "TZS",
    status_value: JobStatus = JobStatus.awaiting_payment,
    payment_status_value: PaymentStatus = PaymentStatus.pending,
):
    return SimpleNamespace(
        total_cost=total_cost,
        currency=currency,
        status=status_value,
        payment_status=payment_status_value,
    )


def test_normalize_msisdn_trims_symbols_and_keeps_valid_digits() -> None:
    assert _normalize_msisdn(" +255 778-415-671 ") == "+255778415671"


@pytest.mark.parametrize("raw_msisdn", ["", "12345", "+25577ABC123", "++255778415671"])
def test_normalize_msisdn_rejects_invalid_formats(raw_msisdn: str) -> None:
    with pytest.raises(HTTPException) as exc:
        _normalize_msisdn(raw_msisdn)
    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Invalid MSISDN format" in exc.value.detail


def test_validate_payment_request_state_rejects_amount_mismatch() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request_state(
            payload=_payment_payload(amount=400.0),
            print_job=_print_job(total_cost=500.0),
            latest_pending_payment=None,
        )
    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Payment amount must match job total" in exc.value.detail


def test_validate_payment_request_state_rejects_paid_or_printing_jobs() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request_state(
            payload=_payment_payload(),
            print_job=_print_job(status_value=JobStatus.printed),
            latest_pending_payment=None,
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT
    assert "already paid or in print workflow" in exc.value.detail


def test_validate_payment_request_state_rejects_confirmed_payment_status() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request_state(
            payload=_payment_payload(),
            print_job=_print_job(payment_status_value=PaymentStatus.confirmed),
            latest_pending_payment=None,
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT
    assert "Payment already confirmed" in exc.value.detail


def test_validate_payment_request_state_rejects_existing_pending_payment() -> None:
    pending_payment = SimpleNamespace(provider_request_id="SN_DUPLICATE")
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request_state(
            payload=_payment_payload(),
            print_job=_print_job(),
            latest_pending_payment=pending_payment,
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT
    assert "pending payment already exists" in exc.value.detail


def test_validate_payment_request_state_accepts_valid_payment_creation_context() -> None:
    _validate_payment_request_state(
        payload=_payment_payload(),
        print_job=_print_job(),
        latest_pending_payment=None,
    )
