from app.services.customer_experience import resolve_printer_capabilities, sanitize_customer_experience_config


def test_sanitize_customer_experience_config_keeps_printer_capabilities() -> None:
    payload = {
        "printer_capabilities": {
            "default": {"color_enabled": "false", "a3_enabled": "true"},
            "devices": {
                "pi-kiosk-001": {"color_enabled": True, "a3_enabled": False},
                "pi-kiosk-002": {"color_enabled": "true", "a3_enabled": "true"},
            },
        }
    }

    normalized = sanitize_customer_experience_config(payload)

    assert normalized["printer_capabilities"]["default"]["color_enabled"] is False
    assert normalized["printer_capabilities"]["default"]["a3_enabled"] is True
    assert normalized["printer_capabilities"]["devices"]["pi-kiosk-001"]["color_enabled"] is True
    assert normalized["printer_capabilities"]["devices"]["pi-kiosk-001"]["a3_enabled"] is False
    assert normalized["printer_capabilities"]["devices"]["pi-kiosk-002"]["color_enabled"] is True
    assert normalized["printer_capabilities"]["devices"]["pi-kiosk-002"]["a3_enabled"] is True


def test_resolve_printer_capabilities_prefers_device_override() -> None:
    config = sanitize_customer_experience_config(
        {
            "printer_capabilities": {
                "default": {"color_enabled": True, "a3_enabled": False},
                "devices": {
                    "pi-kiosk-001": {"color_enabled": False, "a3_enabled": True},
                },
            }
        }
    )

    resolved_device = resolve_printer_capabilities(config=config, device_code="pi-kiosk-001")
    resolved_other = resolve_printer_capabilities(config=config, device_code="pi-kiosk-999")

    assert resolved_device == {"color_enabled": False, "a3_enabled": True}
    assert resolved_other == {"color_enabled": True, "a3_enabled": False}
