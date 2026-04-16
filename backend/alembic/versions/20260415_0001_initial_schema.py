"""Initial Hasnet PrintHub schema

Revision ID: 20260415_0001
Revises:
Create Date: 2026-04-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260415_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


device_status = postgresql.ENUM("online", "offline", "degraded", "maintenance", name="device_status", create_type=False)
printer_status = postgresql.ENUM(
    "unknown",
    "ready",
    "printing",
    "offline",
    "paper_out",
    "paused",
    "error",
    "queue_stuck",
    "low_toner",
    "paper_jam",
    "cover_open",
    name="printer_status",
    create_type=False,
)
job_status = postgresql.ENUM(
    "created",
    "awaiting_payment",
    "paid",
    "queued",
    "dispatched",
    "printing",
    "printed",
    "failed",
    "cancelled",
    "expired",
    name="job_status",
    create_type=False,
)
color_mode = postgresql.ENUM("bw", "color", name="color_mode", create_type=False)
payment_method = postgresql.ENUM("mpesa", "airtel", "tigo", "snippe", name="payment_method", create_type=False)
payment_status = postgresql.ENUM(
    "initiated",
    "pending",
    "confirmed",
    "failed",
    "expired",
    "refunded",
    name="payment_status",
    create_type=False,
)
alert_type = postgresql.ENUM(
    "device_offline",
    "device_recovered",
    "printer_offline",
    "paper_out",
    "printer_error",
    "job_failed",
    "queue_stuck",
    name="alert_type",
    create_type=False,
)
alert_status = postgresql.ENUM("active", "resolved", name="alert_status", create_type=False)
alert_severity = postgresql.ENUM("info", "warning", "critical", name="alert_severity", create_type=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    bind = op.get_bind()
    device_status.create(bind, checkfirst=True)
    printer_status.create(bind, checkfirst=True)
    job_status.create(bind, checkfirst=True)
    color_mode.create(bind, checkfirst=True)
    payment_method.create(bind, checkfirst=True)
    payment_status.create(bind, checkfirst=True)
    alert_type.create(bind, checkfirst=True)
    alert_status.create(bind, checkfirst=True)
    alert_severity.create(bind, checkfirst=True)

    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("email", name="uq_admin_users_email"),
    )

    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("device_code", sa.String(length=100), nullable=False),
        sa.Column("subdomain", sa.String(length=255), nullable=False),
        sa.Column("site_name", sa.String(length=255), nullable=False),
        sa.Column("status", device_status, nullable=False, server_default="offline"),
        sa.Column("printer_status", printer_status, nullable=False, server_default="unknown"),
        sa.Column("printer_name", sa.String(length=255), nullable=True),
        sa.Column("local_ip", postgresql.INET(), nullable=True),
        sa.Column("public_ip", postgresql.INET(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_interval_sec", sa.Integer(), nullable=False, server_default="45"),
        sa.Column("api_token_hash", sa.Text(), nullable=False),
        sa.Column("agent_version", sa.String(length=50), nullable=True),
        sa.Column("firmware_version", sa.String(length=50), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("device_code", name="uq_devices_device_code"),
        sa.UniqueConstraint("subdomain", name="uq_devices_subdomain"),
    )

    op.create_table(
        "pricing_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bw_price_per_page", sa.Numeric(12, 2), nullable=False),
        sa.Column("color_price_per_page", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="TZS"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "print_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_file_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("file_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=False),
        sa.Column("color", color_mode, nullable=False),
        sa.Column("copies", sa.Integer(), nullable=False),
        sa.Column("price_per_page", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False, server_default="TZS"),
        sa.Column("status", job_status, nullable=False, server_default="created"),
        sa.Column("payment_method", payment_method, nullable=True),
        sa.Column("payment_status", payment_status, nullable=False, server_default="initiated"),
        sa.Column("transaction_reference", sa.String(length=255), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("file_size_bytes > 0 AND file_size_bytes <= 10485760", name="ck_print_jobs_file_size"),
        sa.CheckConstraint("pages > 0", name="ck_print_jobs_pages"),
        sa.CheckConstraint("copies > 0 AND copies <= 500", name="ck_print_jobs_copies"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
    )

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("print_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="snippe"),
        sa.Column("method", payment_method, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False, server_default="TZS"),
        sa.Column("status", payment_status, nullable=False, server_default="initiated"),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("provider_transaction_ref", sa.String(length=255), nullable=True),
        sa.Column("provider_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("webhook_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["print_job_id"], ["print_jobs.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("print_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", alert_type, nullable=False),
        sa.Column("severity", alert_severity, nullable=False),
        sa.Column("status", alert_status, nullable=False, server_default="active"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notify_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["print_job_id"], ["print_jobs.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("print_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["print_job_id"], ["print_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_devices_last_seen", "devices", ["last_seen_at"])
    op.create_index("ix_print_jobs_device_status_created", "print_jobs", ["device_id", "status", "created_at"])
    op.create_index("ix_payments_job_status", "payments", ["print_job_id", "status", "created_at"])
    op.create_index("ix_logs_device_created", "logs", ["device_id", "created_at"])
    op.create_index("ix_alerts_device_status", "alerts", ["device_id", "status", "last_seen_at"])
    op.create_index(
        "ux_alerts_active_dedupe",
        "alerts",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("ux_alerts_active_dedupe", table_name="alerts")
    op.drop_index("ix_alerts_device_status", table_name="alerts")
    op.drop_index("ix_logs_device_created", table_name="logs")
    op.drop_index("ix_payments_job_status", table_name="payments")
    op.drop_index("ix_print_jobs_device_status_created", table_name="print_jobs")
    op.drop_index("ix_devices_last_seen", table_name="devices")

    op.drop_table("logs")
    op.drop_table("alerts")
    op.drop_table("payments")
    op.drop_table("print_jobs")
    op.drop_table("pricing_rules")
    op.drop_table("devices")
    op.drop_table("admin_users")

    bind = op.get_bind()
    alert_severity.drop(bind, checkfirst=True)
    alert_status.drop(bind, checkfirst=True)
    alert_type.drop(bind, checkfirst=True)
    payment_status.drop(bind, checkfirst=True)
    payment_method.drop(bind, checkfirst=True)
    color_mode.drop(bind, checkfirst=True)
    job_status.drop(bind, checkfirst=True)
    printer_status.drop(bind, checkfirst=True)
    device_status.drop(bind, checkfirst=True)
