import json
from pathlib import Path

DEFAULT_PRICING_CONFIG = {
    "bw_price_per_page": 500.0,
    "color_price_per_page": 500.0,
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
    currency = payload.get("currency")

    try:
        bw_value = float(bw)
    except (TypeError, ValueError):
        bw_value = float(DEFAULT_PRICING_CONFIG["bw_price_per_page"])

    try:
        color_value = float(color)
    except (TypeError, ValueError):
        color_value = float(DEFAULT_PRICING_CONFIG["color_price_per_page"])

    currency_value = str(currency or DEFAULT_PRICING_CONFIG["currency"]).strip().upper()
    if len(currency_value) != 3 or not currency_value.isalpha():
        currency_value = str(DEFAULT_PRICING_CONFIG["currency"])

    return {
        "bw_price_per_page": max(0.0, bw_value),
        "color_price_per_page": max(0.0, color_value),
        "currency": currency_value,
    }


def save_pricing_config(*, bw_price_per_page: float, color_price_per_page: float, currency: str) -> dict[str, float | str]:
    payload = {
        "bw_price_per_page": round(max(0.0, float(bw_price_per_page)), 2),
        "color_price_per_page": round(max(0.0, float(color_price_per_page)), 2),
        "currency": currency.strip().upper(),
    }
    _PRICING_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PRICING_CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
