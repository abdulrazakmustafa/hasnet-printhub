from datetime import datetime, timezone

from app.api.routes import devices as device_routes
from app.models.enums import AlertSeverity, AlertType
from app.schemas.device import DeviceHeartbeatRequest


def _payload(**overrides) -> DeviceHeartbeatRequest:
    base = {
        "device_code": "pi-kiosk-001",
        "status": "online",
        "printer_status": "ready",
        "printer_name": "HP-M506",
        "printer_details": "Printer ready",
        "active_error": None,
        "timestamp": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return DeviceHeartbeatRequest(**base)


def _by_type(payload: DeviceHeartbeatRequest) -> dict[AlertType, tuple[AlertSeverity, str, str]]:
    specs = device_routes._build_active_alert_specs(payload)
    return {
        alert_type: (severity, title, description)
        for alert_type, severity, title, description in specs
    }


def test_build_active_alert_specs_adds_low_level_threshold_alerts(monkeypatch) -> None:
    monkeypatch.setattr(device_routes.settings, "alert_low_paper_pct", 20)
    monkeypatch.setattr(device_routes.settings, "alert_low_toner_pct", 15)
    monkeypatch.setattr(device_routes.settings, "alert_low_ink_pct", 10)

    by_type = _by_type(
        _payload(
            paper_level_pct=12,
            toner_level_pct=9,
            ink_level_pct=7,
            printer_details="Paper level=12 toner=9 ink=7",
        )
    )

    assert by_type[AlertType.paper_out][0] == AlertSeverity.warning
    assert "12%" in by_type[AlertType.paper_out][1]
    assert by_type[AlertType.printer_error][0] == AlertSeverity.warning
    assert "threshold" in by_type[AlertType.printer_error][2].lower()


def test_build_active_alert_specs_promotes_zero_consumable_to_critical(monkeypatch) -> None:
    monkeypatch.setattr(device_routes.settings, "alert_low_paper_pct", 20)
    monkeypatch.setattr(device_routes.settings, "alert_low_toner_pct", 20)

    by_type = _by_type(_payload(paper_level_pct=0, toner_level_pct=0))

    assert by_type[AlertType.paper_out][0] == AlertSeverity.critical
    assert by_type[AlertType.printer_error][0] == AlertSeverity.critical


def test_append_recent_error_event_dedupes_consecutive_signatures() -> None:
    metadata: dict[str, object] = {}
    now = datetime.now(timezone.utc)
    payload = _payload(printer_status="offline", active_error="offline: no printer connected")

    device_routes._append_recent_error_event(metadata=metadata, payload=payload, now_utc=now)
    device_routes._append_recent_error_event(metadata=metadata, payload=payload, now_utc=now)

    history = metadata.get("recent_errors")
    assert isinstance(history, list)
    assert len(history) == 1
    assert history[0]["printer_status"] == "offline"

