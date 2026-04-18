from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_customer_start_redirects_to_customer_app(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_reconcile_enabled", False)

    with TestClient(app) as client:
        response = client.get("/customer-start", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers.get("location") == "/customer-app/?entry=qr"


def test_customer_short_redirects_to_customer_app(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_reconcile_enabled", False)

    with TestClient(app) as client:
        response = client.get("/customer", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers.get("location") == "/customer-app/?entry=qr"
