import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PrintJobCreateRequest(BaseModel):
    pages: int = Field(..., gt=0)
    copies: int = Field(..., gt=0, le=500)
    color: str
    device_code: str = "prototype-local"
    original_file_name: str = "pending-upload.pdf"
    storage_key: str | None = None
    bw_price_per_page: float = Field(..., ge=0)
    color_price_per_page: float = Field(..., ge=0)
    currency: str = "TZS"


class PrintJobCreateResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    total_cost: float
    currency: str


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
