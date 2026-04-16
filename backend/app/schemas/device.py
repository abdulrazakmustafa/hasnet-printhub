from datetime import datetime

from pydantic import BaseModel


class DeviceHeartbeatRequest(BaseModel):
    device_code: str
    status: str
    printer_status: str
    local_ip: str | None = None
    public_ip: str | None = None
    site_name: str | None = None
    agent_version: str | None = None
    firmware_version: str | None = None
    timestamp: datetime | None = None


class DeviceHeartbeatResponse(BaseModel):
    status: str
    device_code: str
    device_status: str
    printer_status: str
    heartbeat_at: datetime


class DeviceNextJobResponse(BaseModel):
    status: str
    job_id: str | None = None
    storage_key: str | None = None
    original_file_name: str | None = None
    copies: int | None = None
    color: str | None = None
    pages: int | None = None


class DeviceJobStatusUpdateRequest(BaseModel):
    status: str
    failure_reason: str | None = None
