import pytest
from fastapi import HTTPException, status
from types import SimpleNamespace

from app.api.routes.admin import (
    _extract_customer_msisdn,
    _extract_customer_name,
    _parse_payment_method_filter,
    _parse_payment_status_filter,
)
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


def test_extract_customer_details_from_snippe_request_payload() -> None:
    payment = SimpleNamespace(
        provider_payload={
            "request": {
                "phone_number": "+255712345678",
                "customer": {"firstname": "Abdul", "lastname": "Razak"},
            }
        }
    )
    assert _extract_customer_name(payment) == "Abdul Razak"
    assert _extract_customer_msisdn(payment) == "+255712345678"


def test_extract_customer_details_from_mixx_payload_variants() -> None:
    payment = SimpleNamespace(
        provider_payload={
            "request": {"CustomerMSISDN": "255778000111"},
            "last_webhook": {"customer_name": "Demo Customer"},
        }
    )
    assert _extract_customer_name(payment) == "Demo Customer"
    assert _extract_customer_msisdn(payment) == "255778000111"
