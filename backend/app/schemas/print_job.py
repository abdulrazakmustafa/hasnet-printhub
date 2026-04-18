import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class PrintJobCreateRequest(BaseModel):
    pages: int = Field(..., gt=0, le=2000)
    copies: int = Field(..., gt=0, le=500)
    color: str
    device_code: str = "prototype-local"
    original_file_name: str = "pending-upload.pdf"
    storage_key: str | None = None
    upload_id: str | None = None
    bw_price_per_page: float = Field(..., ge=0)
    color_price_per_page: float = Field(..., ge=0)
    currency: str = "TZS"

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"bw", "color"}:
            raise ValueError("Unsupported color mode. Use 'bw' or 'color'.")
        return normalized

    @field_validator("device_code")
    @classmethod
    def validate_device_code(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return "prototype-local"
        if len(normalized) > 64:
            raise ValueError("device_code must be 64 characters or fewer.")
        if any(ch.isspace() for ch in normalized):
            raise ValueError("device_code must not contain spaces.")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
        if any(ch not in allowed for ch in normalized):
            raise ValueError("device_code may only contain letters, digits, '.', '-', and '_'.")
        return normalized

    @field_validator("original_file_name")
    @classmethod
    def validate_original_file_name(cls, value: str) -> str:
        normalized = value.strip() or "pending-upload.pdf"
        if len(normalized) > 255:
            raise ValueError("original_file_name must be 255 characters or fewer.")
        if "/" in normalized or "\\" in normalized:
            raise ValueError("original_file_name must not include path separators.")
        return normalized

    @field_validator("storage_key")
    @classmethod
    def validate_storage_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 1024:
            raise ValueError("storage_key must be 1024 characters or fewer.")
        if normalized.lower().startswith("file://"):
            raise ValueError("storage_key must not use the file:// scheme.")
        if "\x00" in normalized:
            raise ValueError("storage_key contains unsupported characters.")

        parsed = urlparse(normalized)
        if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError("storage_key URL scheme must be http or https.")
        if parsed.scheme and not parsed.netloc:
            raise ValueError("storage_key URL must include a hostname.")

        path = parsed.path if parsed.scheme else normalized
        segments = [segment for segment in path.replace("\\", "/").split("/") if segment]
        if any(segment == ".." for segment in segments):
            raise ValueError("storage_key must not contain parent-directory traversal.")
        return normalized

    @field_validator("upload_id")
    @classmethod
    def validate_upload_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        try:
            uuid.UUID(normalized)
        except ValueError as exc:
            raise ValueError("upload_id must be a valid UUID.") from exc
        return normalized

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency must be a 3-letter ISO code, for example TZS.")
        return normalized


class PrintJobCreateResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    total_cost: float
    currency: str


class PrintJobUploadResponse(BaseModel):
    upload_id: str
    storage_key: str
    file_name: str
    file_size_bytes: int
    content_type: str
    sha256: str


class CustomerTimelineEvent(BaseModel):
    code: str
    label: str
    state: str
    at: datetime | None = None
    detail: str | None = None


class CustomerPaymentReceipt(BaseModel):
    payment_id: uuid.UUID
    provider: str
    provider_request_id: str | None = None
    provider_transaction_ref: str | None = None
    payment_status: str
    amount: float
    currency: str
    requested_at: datetime | None = None
    confirmed_at: datetime | None = None
    webhook_received_at: datetime | None = None
    updated_at: datetime | None = None


class PrintJobCustomerStatusResponse(BaseModel):
    contract_version: str = "customer-status-v1"
    job_id: uuid.UUID
    stage: str
    message: str
    next_action: str

    job_status: str
    payment_status: str
    payment_method: str | None = None
    transaction_reference: str | None = None

    total_cost: float
    currency: str
    pages: int
    copies: int
    color: str

    provider: str | None = None
    provider_request_id: str | None = None
    provider_transaction_ref: str | None = None

    created_at: datetime | None = None
    paid_at: datetime | None = None
    printed_at: datetime | None = None
    failure_reason: str | None = None
    timeline: list[CustomerTimelineEvent] = Field(default_factory=list)
    receipt: CustomerPaymentReceipt | None = None


class PrintJobCustomerReceiptResponse(BaseModel):
    contract_version: str = "customer-receipt-v1"
    job_id: uuid.UUID
    stage: str
    headline: str
    message: str
    next_action: str

    job_status: str
    payment_status: str
    payment_method: str | None = None
    transaction_reference: str | None = None

    total_cost: float
    currency: str
    pages: int
    copies: int
    color: str

    issued_at: datetime
    timeline: list[CustomerTimelineEvent] = Field(default_factory=list)
    receipt: CustomerPaymentReceipt | None = None
