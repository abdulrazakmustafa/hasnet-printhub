import uuid

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


class PaymentWebhookPayload(BaseModel):
    transaction_reference: str
    provider_request_id: str
    status: str
    amount: float | None = None
    raw_payload: dict = Field(default_factory=dict)
