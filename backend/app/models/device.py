import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy import Enum as SQLAEnum
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.enums import DeviceStatus, PrinterStatus
from app.models.mixins import TimestampMixin


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    subdomain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    site_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(
        SQLAEnum(DeviceStatus, name="device_status"), nullable=False, default=DeviceStatus.offline
    )
    printer_status: Mapped[PrinterStatus] = mapped_column(
        SQLAEnum(PrinterStatus, name="printer_status"), nullable=False, default=PrinterStatus.unknown
    )
    printer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    local_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    public_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=45, server_default="45")
    api_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    print_jobs = relationship("PrintJob", back_populates="device")
    alerts = relationship("Alert", back_populates="device")
    logs = relationship("LogEntry", back_populates="device")
    pricing_rules = relationship("PricingRule", back_populates="device")

