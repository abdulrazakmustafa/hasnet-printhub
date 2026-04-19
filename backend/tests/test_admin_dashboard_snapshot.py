from datetime import datetime, timezone

from app.api.routes import admin as admin_routes


def test_admin_dashboard_snapshot_composes_sources(monkeypatch) -> None:
    seen: dict[str, int] = {}

    def fake_report_today(*, device_code=None, db):
        assert db == "fake-db"
        assert device_code == "pi-kiosk-001"
        return {
            "window": {"start_utc": datetime(2026, 4, 18, tzinfo=timezone.utc), "end_utc": datetime(2026, 4, 19, tzinfo=timezone.utc)},
            "payments": {"confirmed": 3, "confirmed_amount": 1500.0},
            "jobs": {"printed": 2},
            "devices": {"active": 2, "online": 2},
            "alerts": {"active": 0},
        }

    def fake_admin_payments(*, limit, db, payment_status=None, method=None, provider=None, device_code=None, lifecycle=None):
        assert db == "fake-db"
        assert payment_status is None
        assert method is None
        assert provider is None
        assert device_code == "pi-kiosk-001"
        assert lifecycle is None
        seen["recent_payments_limit"] = limit
        return {"count": 1, "items": [{"payment_id": "p1"}]}

    def fake_pending_incidents(*, limit, db, escalated_only=False, method=None, device_code=None):
        assert db == "fake-db"
        assert escalated_only is False
        assert method is None
        assert device_code == "pi-kiosk-001"
        seen["pending_incidents_limit"] = limit
        return {"count": 2, "escalated_count": 1, "escalation_threshold_minutes": 10, "items": [{"payment_id": "p2"}]}

    def fake_monitor(*, db, device_code=None):
        assert db == "fake-db"
        assert device_code == "pi-kiosk-001"
        return {
            "device_count": 1,
            "summary": {"avg_uptime_hours": 10.5, "total_error_events_24h": 1, "total_active_alerts": 0, "online_devices": 1},
            "devices": [{"device_code": "pi-kiosk-001"}],
        }

    monkeypatch.setattr(admin_routes, "admin_report_today", fake_report_today)
    monkeypatch.setattr(admin_routes, "admin_payments", fake_admin_payments)
    monkeypatch.setattr(admin_routes, "admin_pending_payment_incidents", fake_pending_incidents)
    monkeypatch.setattr(admin_routes, "_build_device_monitor", fake_monitor)

    payload = admin_routes.admin_dashboard_snapshot(
        recent_payments_limit=7,
        pending_incidents_limit=9,
        device_code="pi-kiosk-001",
        db="fake-db",
    )

    assert seen["recent_payments_limit"] == 7
    assert seen["pending_incidents_limit"] == 9
    assert payload["kpis"]["confirmed_payments_today"] == 3
    assert payload["kpis"]["pending_incidents"] == 2
    assert payload["kpis"]["escalated_pending_incidents"] == 1
    assert payload["recent_payments"]["count"] == 1
    assert payload["pending_incidents"]["escalation_threshold_minutes"] == 10
    assert payload["monitor"]["summary"]["avg_uptime_hours"] == 10.5
    assert payload["generated_at_utc"].tzinfo is not None
