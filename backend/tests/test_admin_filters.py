import pytest
from fastapi import HTTPException, status

from app.api.routes.admin import _parse_payment_method_filter, _parse_payment_status_filter
from app.models.enums import PaymentMethod, PaymentStatus


def test_parse_payment_status_filter_blank_returns_none() -> None:
    assert _parse_payment_status_filter(None) is None
    assert _parse_payment_status_filter("   ") is None


def test_parse_payment_status_filter_valid_value() -> None:
    assert _parse_payment_status_filter(" confirmed ") == PaymentStatus.confirmed


def test_parse_payment_status_filter_invalid_value() -> None:
    with pytest.raises(HTTPException) as exc:
        _parse_payment_status_filter("done")

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "status must be one of" in exc.value.detail


def test_parse_payment_method_filter_blank_returns_none() -> None:
    assert _parse_payment_method_filter(None) is None
    assert _parse_payment_method_filter("   ") is None


def test_parse_payment_method_filter_valid_value() -> None:
    assert _parse_payment_method_filter(" mpesa ") == PaymentMethod.mpesa


def test_parse_payment_method_filter_invalid_value() -> None:
    with pytest.raises(HTTPException) as exc:
        _parse_payment_method_filter("visa")

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "method must be one of" in exc.value.detail
