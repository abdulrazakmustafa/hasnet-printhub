import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.api.routes.admin import _build_pending_incident_item
from app.core.config import settings
from app.models.enums import JobStatus, PaymentMethod, PaymentStatus


def _fake_pending_payment(*, requested_at: datetime):
    return SimpleNamespace(
        id=uuid.uuid4(),
        provider="snippe",
        method=PaymentMethod.mpesa,
        status=PaymentStatus.pending,
        amount=1000,
        currency="TZS",
        provider_request_id="SN-TEST-001",
        provider_transaction_ref=None,
        requested_at=requested_at,
        updated_at=requested_at + timedelta(minutes=1),
    )


def _fake_job(*, created_at: datetime):
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=JobStatus.awaiting_payment,
        payment_status=PaymentStatus.pending,
        created_at=created_at,
    )


def test_build_pending_incident_marks_escalated_after_threshold(monkeypatch) -> None:
    monkeypatch.setattr(settings, "customer_pending_escalation_minutes", 10)
    now_utc = datetime.now(timezone.utc)
    payment = _fake_pending_payment(requested_at=now_utc - timedelta(minutes=15))
    job = _fake_job(created_at=now_utc - timedelta(minutes=20))

    item = _build_pending_incident_item(
        payment=payment,
        job=job,
        resolved_device_code="DEV001",
        now_utc=now_utc,
    )

    assert item["escalated"] is True
    assert item["pending_minutes"] >= 15
    assert item["escalation_threshold_minutes"] == 10
    assert "Run reconcile and verify provider reference now" in item["recommended_action"]


def test_build_pending_incident_uses_job_created_at_when_requested_at_missing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "customer_pending_escalation_minutes", 10)
    now_utc = datetime.now(timezone.utc)
    payment = _fake_pending_payment(requested_at=now_utc)
    payment.requested_at = None
    job = _fake_job(created_at=now_utc - timedelta(minutes=4))

    item = _build_pending_incident_item(
        payment=payment,
        job=job,
        resolved_device_code=None,
        now_utc=now_utc,
    )

    assert item["escalated"] is False
    assert item["pending_minutes"] >= 4
    assert "Await provider confirmation" in item["recommended_action"]
