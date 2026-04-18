import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PaymentCreateRequest(BaseModel):
    print_job_id: uuid.UUID
    amount: float = Field(..., gt=0)
    method: str
    msisdn: str
    customer_first_name: str = "PrintHub"
    customer_last_name: str = "Customer"
    customer_email: str = "customer@hasnet.local"


class PaymentCreateResponse(BaseModel):
    payment_id: uuid.UUID
    status: str
    provider_request_id: str
    checkout_url: str | None = None


class PaymentRetrySafeCreateResponse(BaseModel):
    decision: str
    reconcile_synced: int
    payment: PaymentCreateResponse


class PaymentWebhookPayload(BaseModel):
    transaction_reference: str
    provider_request_id: str
    status: str
    amount: float | None = None
    raw_payload: dict = Field(default_factory=dict)


class PaymentStatusSnapshotResponse(BaseModel):
    payment_id: uuid.UUID
    provider: str
    provider_request_id: str
    provider_transaction_ref: str | None = None
    payment_status: str
    payment_amount: float
    payment_currency: str
    payment_requested_at: datetime | None = None
    payment_confirmed_at: datetime | None = None
    payment_webhook_received_at: datetime | None = None
    payment_updated_at: datetime | None = None

    print_job_id: uuid.UUID | None = None
    print_job_status: str | None = None
    print_job_payment_status: str | None = None
    print_job_paid_at: datetime | None = None
    print_job_printed_at: datetime | None = None
    print_job_failure_reason: str | None = None

    device_code: str | None = None
    device_status: str | None = None
    device_printer_status: str | None = None
