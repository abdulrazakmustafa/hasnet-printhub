import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SQLAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.enums import ColorMode, JobStatus, PaymentMethod, PaymentStatus
from app.models.mixins import TimestampMixin


class PrintJob(Base, TimestampMixin):
    __tablename__ = "print_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"))
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    file_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    pages: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[ColorMode] = mapped_column(SQLAEnum(ColorMode, name="color_mode"), nullable=False)
    copies: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_page: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    total_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="TZS", server_default="TZS")
    status: Mapped[JobStatus] = mapped_column(SQLAEnum(JobStatus, name="job_status"), nullable=False, default=JobStatus.created)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(SQLAEnum(PaymentMethod, name="payment_method"), nullable=True)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        SQLAEnum(PaymentStatus, name="payment_status"), nullable=False, default=PaymentStatus.initiated
    )
    transaction_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device = relationship("Device", back_populates="print_jobs")
    payments = relationship("Payment", back_populates="print_job")
    logs = relationship("LogEntry", back_populates="print_job")
    alerts = relationship("Alert", back_populates="print_job")

