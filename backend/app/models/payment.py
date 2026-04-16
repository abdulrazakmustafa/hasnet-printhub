import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy import Enum as SQLAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.enums import PaymentMethod, PaymentStatus
from app.models.mixins import TimestampMixin


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    print_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("print_jobs.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="snippe", server_default="snippe")
    method: Mapped[PaymentMethod] = mapped_column(SQLAEnum(PaymentMethod, name="payment_method"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="TZS", server_default="TZS")
    status: Mapped[PaymentStatus] = mapped_column(
        SQLAEnum(PaymentStatus, name="payment_status"), nullable=False, default=PaymentStatus.initiated
    )
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_transaction_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    print_job = relationship("PrintJob", back_populates="payments")
    logs = relationship("LogEntry", back_populates="payment")
