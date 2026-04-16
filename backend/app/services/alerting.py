from datetime import datetime, timedelta, timezone

from app.core.config import settings


def should_renotify(last_notified_at: datetime | None) -> bool:
    if last_notified_at is None:
        return True
    window = timedelta(minutes=settings.alert_renotify_minutes)
    return datetime.now(timezone.utc) >= (last_notified_at + window)


def dedupe_key(device_code: str, alert_type: str) -> str:
    return f"{device_code}:{alert_type}"

