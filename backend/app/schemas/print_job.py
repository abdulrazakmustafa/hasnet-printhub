import uuid

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
