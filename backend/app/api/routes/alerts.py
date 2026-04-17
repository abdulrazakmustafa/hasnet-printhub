from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.alert import Alert
from app.models.device import Device
from app.models.enums import AlertSeverity, AlertStatus
from app.schemas.alert import AlertResponse

router = APIRouter()


@router.get("")
def list_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    alert_status: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    device_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, list[AlertResponse]]:
    normalized_status: AlertStatus | None = None
    if alert_status and alert_status.strip():
        try:
            normalized_status = AlertStatus(alert_status.strip().lower())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="status must be one of: active, resolved",
            ) from exc

    normalized_severity: AlertSeverity | None = None
    if severity and severity.strip():
        try:
            normalized_severity = AlertSeverity(severity.strip().lower())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="severity must be one of: info, warning, critical",
            ) from exc

    query = select(Alert, Device.device_code).join(Device, Device.id == Alert.device_id)
    if normalized_status is not None:
        query = query.where(Alert.status == normalized_status)
    if normalized_severity is not None:
        query = query.where(Alert.severity == normalized_severity)
    if device_code and device_code.strip():
        query = query.where(Device.device_code == device_code.strip())

    rows = db.execute(query.order_by(Alert.last_seen_at.desc(), Alert.created_at.desc()).limit(limit)).all()

    items = [
        AlertResponse(
            id=str(alert.id),
            type=alert.type.value,
            severity=alert.severity.value,
            status=alert.status.value,
            title=alert.title,
            device_code=code,
            first_seen_at=alert.first_seen_at,
            last_seen_at=alert.last_seen_at,
            resolved_at=alert.resolved_at,
        )
        for alert, code in rows
    ]

    return {"items": items}
