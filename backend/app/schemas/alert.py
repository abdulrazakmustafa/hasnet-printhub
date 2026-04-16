from datetime import datetime

from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: str
    type: str
    severity: str
    status: str
    title: str
    device_code: str
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None = None

