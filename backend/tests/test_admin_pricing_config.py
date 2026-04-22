import pytest
from fastapi import HTTPException, status

from app.api.routes import admin as admin_routes


def test_admin_get_pricing_config_returns_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        admin_routes,
        "get_pricing_config",
        lambda: {
            "bw_price_per_page": 500.0,
            "color_price_per_page": 800.0,
            "a4_bw_price_per_page": 500.0,
            "a4_color_price_per_page": 800.0,
            "a3_bw_price_per_page": 600.0,
            "a3_color_price_per_page": 900.0,
            "currency": "TZS",
        },
    )

    result = admin_routes.admin_get_pricing_config()

    assert result.bw_price_per_page == 500.0
    assert result.color_price_per_page == 800.0
    assert result.a4_bw_price_per_page == 500.0
    assert result.a4_color_price_per_page == 800.0
    assert result.a3_bw_price_per_page == 600.0
    assert result.a3_color_price_per_page == 900.0
    assert result.currency == "TZS"


def test_admin_update_pricing_config_rejects_bad_currency() -> None:
    payload = admin_routes.AdminPricingConfigUpdateRequest(
        bw_price_per_page=500.0,
        color_price_per_page=900.0,
        a4_bw_price_per_page=500.0,
        a4_color_price_per_page=900.0,
        a3_bw_price_per_page=700.0,
        a3_color_price_per_page=1100.0,
        currency="TZ1",
    )
    with pytest.raises(HTTPException) as exc:
        admin_routes.admin_update_pricing_config(payload)

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "3-letter ISO code" in exc.value.detail


def test_admin_update_pricing_config_saves(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_save(
        *,
        bw_price_per_page: float,
        color_price_per_page: float,
        a4_bw_price_per_page: float,
        a4_color_price_per_page: float,
        a3_bw_price_per_page: float,
        a3_color_price_per_page: float,
        currency: str,
    ):
        captured["bw"] = bw_price_per_page
        captured["color"] = color_price_per_page
        captured["a4_bw"] = a4_bw_price_per_page
        captured["a4_color"] = a4_color_price_per_page
        captured["a3_bw"] = a3_bw_price_per_page
        captured["a3_color"] = a3_color_price_per_page
        captured["currency"] = currency
        return {
            "bw_price_per_page": bw_price_per_page,
            "color_price_per_page": color_price_per_page,
            "a4_bw_price_per_page": a4_bw_price_per_page,
            "a4_color_price_per_page": a4_color_price_per_page,
            "a3_bw_price_per_page": a3_bw_price_per_page,
            "a3_color_price_per_page": a3_color_price_per_page,
            "currency": currency,
        }

    monkeypatch.setattr(admin_routes, "save_pricing_config", _fake_save)

    payload = admin_routes.AdminPricingConfigUpdateRequest(
        bw_price_per_page=500.0,
        color_price_per_page=900.0,
        a4_bw_price_per_page=500.0,
        a4_color_price_per_page=900.0,
        a3_bw_price_per_page=700.0,
        a3_color_price_per_page=1100.0,
        currency="tzs",
    )
    result = admin_routes.admin_update_pricing_config(payload)

    assert captured["bw"] == 500.0
    assert captured["color"] == 900.0
    assert captured["a4_bw"] == 500.0
    assert captured["a4_color"] == 900.0
    assert captured["a3_bw"] == 700.0
    assert captured["a3_color"] == 1100.0
    assert captured["currency"] == "TZS"
    assert result.currency == "TZS"
