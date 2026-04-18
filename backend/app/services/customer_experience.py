from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.models.device import Device
from app.models.enums import DeviceStatus, PrinterStatus

_CUSTOMER_EXPERIENCE_CONFIG_PATH = Path(__file__).resolve().parents[2] / "assets" / "customer-experience-config.json"

_PRINTER_BLOCKED_STATUSES = {
    PrinterStatus.unknown,
    PrinterStatus.offline,
    PrinterStatus.paper_out,
    PrinterStatus.paused,
    PrinterStatus.error,
    PrinterStatus.queue_stuck,
    PrinterStatus.paper_jam,
    PrinterStatus.cover_open,
}

_DEVICE_BLOCKED_STATUSES = {DeviceStatus.offline, DeviceStatus.maintenance}

DEFAULT_CUSTOMER_EXPERIENCE_CONFIG: dict[str, Any] = {
    "active_device_code": "pi-kiosk-001",
    "site_strip_text": "Driven by Innovation, Powered by Engineering! Enginnovation",
    "theme": {
        "brand_blue": "#272365",
        "brand_blue_2": "#1e1a54",
        "brand_orange": "#f47c20",
        "brand_orange_2": "#ff9a3d",
        "paper": "#f3f4f8",
        "surface": "#ffffff",
        "ink": "#1c2240",
        "ink_soft": "#5a6284",
    },
    "content": {
        "brand_title": "PrintHub",
        "brand_note": "Simple, secure, and fast self-service printing kiosk.",
        "welcome_title": "Karibu Hasnet PrintHub",
        "welcome_lead": "Upload your PDF document and follow simple steps to complete your print.",
        "support_phone": "+255 777 019 901",
        "payment_title": "Payment Details",
        "payment_lead": "Enter details and tap Pay to Print.",
        "finish_success_title": "Printing Successful",
        "finish_success_message": "Asante! Your document has been printed successfully. Karibu tena.",
    },
    "chips": [
        "Payment-verified printing",
        "Auto page detection",
        "Instant status updates",
    ],
    "flow": {
        "show_stepper": True,
        "hide_payment_method": True,
        "default_payment_method": "mpesa",
    },
    "operations": {
        "uploads_enabled": True,
        "payments_enabled": True,
        "pause_reason": "",
        "block_upload_when_printer_unready": True,
        "block_payment_when_printer_unready": True,
        "printer_unready_message": "Printer is currently unavailable. Please contact support staff.",
    },
    "hotspot": {
        "enabled": False,
        "ssid": "HPH-KIOSK-001",
        "passphrase": "",
        "wifi_security": "WPA",
        "gateway_ip": "10.55.0.1",
        "entry_path": "/customer-start",
    },
}


def _safe_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _safe_text(value: object, *, default: str = "", max_len: int = 400) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    return text[:max_len]


def _safe_hex_color(value: object, *, fallback: str) -> str:
    candidate = str(value or "").strip()
    if len(candidate) == 7 and candidate.startswith("#"):
        is_hex = all(ch in "0123456789abcdefABCDEF" for ch in candidate[1:])
        if is_hex:
            return candidate
    return fallback


def _safe_ipv4(value: object, *, fallback: str) -> str:
    candidate = str(value or "").strip()
    parts = candidate.split(".")
    if len(parts) != 4:
        return fallback
    for part in parts:
        if not part.isdigit():
            return fallback
        parsed = int(part)
        if parsed < 0 or parsed > 255:
            return fallback
    return candidate


def _load_raw_customer_experience_payload() -> dict[str, Any]:
    if not _CUSTOMER_EXPERIENCE_CONFIG_PATH.exists():
        return {}
    try:
        payload = json.loads(_CUSTOMER_EXPERIENCE_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def sanitize_customer_experience_config(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    defaults = DEFAULT_CUSTOMER_EXPERIENCE_CONFIG
    out = deepcopy(defaults)

    out["active_device_code"] = _safe_text(
        payload.get("active_device_code"),
        default=defaults["active_device_code"],
        max_len=120,
    ) or defaults["active_device_code"]
    out["site_strip_text"] = _safe_text(
        payload.get("site_strip_text"),
        default=defaults["site_strip_text"],
        max_len=200,
    ) or defaults["site_strip_text"]

    source_theme = _safe_dict(payload.get("theme"))
    for key, fallback in defaults["theme"].items():
        out["theme"][key] = _safe_hex_color(source_theme.get(key), fallback=fallback)

    source_content = _safe_dict(payload.get("content"))
    out["content"]["brand_title"] = _safe_text(
        source_content.get("brand_title"),
        default=defaults["content"]["brand_title"],
        max_len=60,
    )
    out["content"]["brand_note"] = _safe_text(
        source_content.get("brand_note"),
        default=defaults["content"]["brand_note"],
        max_len=180,
    )
    out["content"]["welcome_title"] = _safe_text(
        source_content.get("welcome_title"),
        default=defaults["content"]["welcome_title"],
        max_len=80,
    )
    out["content"]["welcome_lead"] = _safe_text(
        source_content.get("welcome_lead"),
        default=defaults["content"]["welcome_lead"],
        max_len=220,
    )
    out["content"]["support_phone"] = _safe_text(
        source_content.get("support_phone"),
        default=defaults["content"]["support_phone"],
        max_len=40,
    )
    out["content"]["payment_title"] = _safe_text(
        source_content.get("payment_title"),
        default=defaults["content"]["payment_title"],
        max_len=80,
    )
    out["content"]["payment_lead"] = _safe_text(
        source_content.get("payment_lead"),
        default=defaults["content"]["payment_lead"],
        max_len=200,
    )
    out["content"]["finish_success_title"] = _safe_text(
        source_content.get("finish_success_title"),
        default=defaults["content"]["finish_success_title"],
        max_len=80,
    )
    out["content"]["finish_success_message"] = _safe_text(
        source_content.get("finish_success_message"),
        default=defaults["content"]["finish_success_message"],
        max_len=220,
    )

    chips = payload.get("chips")
    if isinstance(chips, list):
        normalized = [_safe_text(item, default="", max_len=70) for item in chips]
        normalized = [item for item in normalized if item]
        if normalized:
            out["chips"] = normalized[:6]

    source_flow = _safe_dict(payload.get("flow"))
    out["flow"]["show_stepper"] = _safe_bool(
        source_flow.get("show_stepper"),
        default=defaults["flow"]["show_stepper"],
    )
    out["flow"]["hide_payment_method"] = _safe_bool(
        source_flow.get("hide_payment_method"),
        default=defaults["flow"]["hide_payment_method"],
    )
    method = _safe_text(
        source_flow.get("default_payment_method"),
        default=defaults["flow"]["default_payment_method"],
        max_len=20,
    ).lower()
    out["flow"]["default_payment_method"] = method if method in {"mpesa", "airtel", "tigo", "snippe"} else "mpesa"

    source_ops = _safe_dict(payload.get("operations"))
    out["operations"]["uploads_enabled"] = _safe_bool(
        source_ops.get("uploads_enabled"),
        default=defaults["operations"]["uploads_enabled"],
    )
    out["operations"]["payments_enabled"] = _safe_bool(
        source_ops.get("payments_enabled"),
        default=defaults["operations"]["payments_enabled"],
    )
    out["operations"]["pause_reason"] = _safe_text(
        source_ops.get("pause_reason"),
        default=defaults["operations"]["pause_reason"],
        max_len=240,
    )
    out["operations"]["block_upload_when_printer_unready"] = _safe_bool(
        source_ops.get("block_upload_when_printer_unready"),
        default=defaults["operations"]["block_upload_when_printer_unready"],
    )
    out["operations"]["block_payment_when_printer_unready"] = _safe_bool(
        source_ops.get("block_payment_when_printer_unready"),
        default=defaults["operations"]["block_payment_when_printer_unready"],
    )
    out["operations"]["printer_unready_message"] = _safe_text(
        source_ops.get("printer_unready_message"),
        default=defaults["operations"]["printer_unready_message"],
        max_len=240,
    )

    source_hotspot = _safe_dict(payload.get("hotspot"))
    out["hotspot"]["enabled"] = _safe_bool(
        source_hotspot.get("enabled"),
        default=defaults["hotspot"]["enabled"],
    )
    out["hotspot"]["ssid"] = _safe_text(
        source_hotspot.get("ssid"),
        default=defaults["hotspot"]["ssid"],
        max_len=32,
    ) or defaults["hotspot"]["ssid"]
    out["hotspot"]["passphrase"] = _safe_text(
        source_hotspot.get("passphrase"),
        default=defaults["hotspot"]["passphrase"],
        max_len=63,
    )
    out["hotspot"]["gateway_ip"] = _safe_ipv4(
        source_hotspot.get("gateway_ip"),
        fallback=defaults["hotspot"]["gateway_ip"],
    )
    security = _safe_text(
        source_hotspot.get("wifi_security"),
        default=defaults["hotspot"]["wifi_security"],
        max_len=10,
    ).upper()
    out["hotspot"]["wifi_security"] = security if security in {"WPA", "WEP", "NOPASS"} else "WPA"
    entry_path = _safe_text(
        source_hotspot.get("entry_path"),
        default=defaults["hotspot"]["entry_path"],
        max_len=80,
    )
    if not entry_path.startswith("/"):
        entry_path = "/" + entry_path
    out["hotspot"]["entry_path"] = entry_path

    return out


def get_customer_experience_config() -> dict[str, Any]:
    if settings.env.strip().lower() == "test" or bool(os.getenv("PYTEST_CURRENT_TEST")):
        return deepcopy(DEFAULT_CUSTOMER_EXPERIENCE_CONFIG)
    payload = _load_raw_customer_experience_payload()
    return sanitize_customer_experience_config(payload)


def save_customer_experience_config(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = sanitize_customer_experience_config(payload)
    _CUSTOMER_EXPERIENCE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOMER_EXPERIENCE_CONFIG_PATH.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return normalized


def _printer_blocking_reason(device: Device) -> str | None:
    if device.status in _DEVICE_BLOCKED_STATUSES:
        return f"Device is {device.status.value}."
    if device.printer_status in _PRINTER_BLOCKED_STATUSES:
        return f"Printer status is {device.printer_status.value}."
    if device.last_seen_at:
        now_utc = datetime.now(timezone.utc)
        last_seen = device.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        age = (now_utc - last_seen).total_seconds()
        if age > settings.device_offline_seconds:
            return f"Device heartbeat is stale ({int(age)}s old)."
    return None


def evaluate_customer_availability(*, device: Device | None, config: dict[str, Any]) -> dict[str, Any]:
    operations = _safe_dict(config.get("operations"))
    pause_reason = _safe_text(operations.get("pause_reason"), default="")
    uploads_enabled = bool(operations.get("uploads_enabled", True))
    payments_enabled = bool(operations.get("payments_enabled", True))

    result = {
        "device_present": device is not None,
        "device_status": device.status.value if device else "unknown",
        "printer_status": device.printer_status.value if device else "unknown",
        "last_seen_at": device.last_seen_at if device else None,
        "can_upload": uploads_enabled,
        "can_pay": payments_enabled,
        "reason_code": "ok",
        "message": "Kiosk is ready.",
    }

    if pause_reason:
        result["reason_code"] = "paused_by_operator"
        result["message"] = pause_reason
    if not uploads_enabled and not payments_enabled:
        result["reason_code"] = "kiosk_paused"
    elif not uploads_enabled:
        result["reason_code"] = "upload_paused"
    elif not payments_enabled:
        result["reason_code"] = "payment_paused"

    if device is None:
        if result["reason_code"] == "ok":
            result["message"] = "Kiosk device is not registered yet."
            result["reason_code"] = "device_missing"
        return result

    printer_reason = _printer_blocking_reason(device)
    if printer_reason:
        if bool(operations.get("block_upload_when_printer_unready", True)):
            result["can_upload"] = False
        if bool(operations.get("block_payment_when_printer_unready", True)):
            result["can_pay"] = False

        if result["reason_code"] in {"ok", "device_missing"}:
            result["reason_code"] = "printer_unready"
            custom = _safe_text(operations.get("printer_unready_message"), default="")
            result["message"] = custom or printer_reason

    return result
