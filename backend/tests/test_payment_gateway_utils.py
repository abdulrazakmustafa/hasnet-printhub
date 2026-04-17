import uuid

import pytest
from fastapi import HTTPException, status

from app.models.enums import PaymentMethod, PaymentStatus
from app.services.payment_gateway import (
    _build_idempotency_key,
    _build_mixx_reference_id,
    _map_method,
    _map_mixx_status,
    _map_snippe_status,
    _response_status_is_success,
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
