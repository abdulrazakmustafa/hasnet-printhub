import json
from pathlib import Path

DEFAULT_PRICING_CONFIG = {
    "bw_price_per_page": 500.0,
    "color_price_per_page": 500.0,
    "a4_bw_price_per_page": 500.0,
    "a4_color_price_per_page": 500.0,
    "a3_bw_price_per_page": 500.0,
    "a3_color_price_per_page": 500.0,
    "currency": "TZS",
}

_PRICING_CONFIG_PATH = Path(__file__).resolve().parents[2] / "assets" / "pricing-config.json"


def get_pricing_config() -> dict[str, float | str]:
    if not _PRICING_CONFIG_PATH.exists():
        return dict(DEFAULT_PRICING_CONFIG)

    try:
        payload = json.loads(_PRICING_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(DEFAULT_PRICING_CONFIG)

    if not isinstance(payload, dict):
        return dict(DEFAULT_PRICING_CONFIG)

    bw = payload.get("bw_price_per_page")
    color = payload.get("color_price_per_page")
    a4_bw = payload.get("a4_bw_price_per_page", bw)
    a4_color = payload.get("a4_color_price_per_page", color)
    a3_bw = payload.get("a3_bw_price_per_page", bw)
    a3_color = payload.get("a3_color_price_per_page", color)
    currency = payload.get("currency")

    try:
        bw_value = float(bw)
    except (TypeError, ValueError):
        bw_value = float(DEFAULT_PRICING_CONFIG["bw_price_per_page"])

    try:
        color_value = float(color)
    except (TypeError, ValueError):
        color_value = float(DEFAULT_PRICING_CONFIG["color_price_per_page"])

    try:
        a4_bw_value = float(a4_bw)
    except (TypeError, ValueError):
        a4_bw_value = bw_value

    try:
        a4_color_value = float(a4_color)
    except (TypeError, ValueError):
        a4_color_value = color_value

    try:
        a3_bw_value = float(a3_bw)
    except (TypeError, ValueError):
        a3_bw_value = bw_value

    try:
        a3_color_value = float(a3_color)
    except (TypeError, ValueError):
        a3_color_value = color_value

    currency_value = str(currency or DEFAULT_PRICING_CONFIG["currency"]).strip().upper()
    if len(currency_value) != 3 or not currency_value.isalpha():
        currency_value = str(DEFAULT_PRICING_CONFIG["currency"])

    return {
        "bw_price_per_page": max(0.0, bw_value),
        "color_price_per_page": max(0.0, color_value),
        "a4_bw_price_per_page": max(0.0, a4_bw_value),
        "a4_color_price_per_page": max(0.0, a4_color_value),
        "a3_bw_price_per_page": max(0.0, a3_bw_value),
        "a3_color_price_per_page": max(0.0, a3_color_value),
        "currency": currency_value,
    }


def save_pricing_config(
    *,
    bw_price_per_page: float,
    color_price_per_page: float,
    a4_bw_price_per_page: float | None = None,
    a4_color_price_per_page: float | None = None,
    a3_bw_price_per_page: float | None = None,
    a3_color_price_per_page: float | None = None,
    currency: str,
) -> dict[str, float | str]:
    normalized_bw = round(max(0.0, float(bw_price_per_page)), 2)
    normalized_color = round(max(0.0, float(color_price_per_page)), 2)
    normalized_a4_bw = round(max(0.0, float(a4_bw_price_per_page if a4_bw_price_per_page is not None else normalized_bw)), 2)
    normalized_a4_color = round(
        max(0.0, float(a4_color_price_per_page if a4_color_price_per_page is not None else normalized_color)),
        2,
    )
    normalized_a3_bw = round(max(0.0, float(a3_bw_price_per_page if a3_bw_price_per_page is not None else normalized_bw)), 2)
    normalized_a3_color = round(
        max(0.0, float(a3_color_price_per_page if a3_color_price_per_page is not None else normalized_color)),
        2,
    )
    payload = {
        "bw_price_per_page": normalized_bw,
        "color_price_per_page": normalized_color,
        "a4_bw_price_per_page": normalized_a4_bw,
        "a4_color_price_per_page": normalized_a4_color,
        "a3_bw_price_per_page": normalized_a3_bw,
        "a3_color_price_per_page": normalized_a3_color,
        "currency": currency.strip().upper(),
    }
    _PRICING_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PRICING_CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
