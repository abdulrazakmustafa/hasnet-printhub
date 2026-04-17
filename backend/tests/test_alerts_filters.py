import pytest
from fastapi import HTTPException, status

from app.api.routes.alerts import list_alerts


class _DummyDB:
    def execute(self, _query):  # pragma: no cover
        raise AssertionError("DB should not be hit when validation fails early")


def test_list_alerts_rejects_invalid_status() -> None:
    with pytest.raises(HTTPException) as exc:
        list_alerts(limit=50, alert_status="bad", severity=None, device_code=None, db=_DummyDB())  # type: ignore[arg-type]

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "status must be one of" in exc.value.detail


def test_list_alerts_rejects_invalid_severity() -> None:
    with pytest.raises(HTTPException) as exc:
        list_alerts(limit=50, alert_status=None, severity="fatal", device_code=None, db=_DummyDB())  # type: ignore[arg-type]

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "severity must be one of" in exc.value.detail
