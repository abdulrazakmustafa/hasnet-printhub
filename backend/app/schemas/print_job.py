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


class PrintJobCustomerStatusResponse(BaseModel):
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
