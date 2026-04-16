from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.payment import PaymentCreateRequest, PaymentCreateResponse
from app.services.payment_gateway import (
    create_payment as create_provider_payment,
    handle_mixx_webhook,
    handle_snippe_webhook,
)

router = APIRouter()


@router.post("/create", response_model=PaymentCreateResponse)
def create_payment(payload: PaymentCreateRequest, db: Session = Depends(get_db)) -> PaymentCreateResponse:
    return create_provider_payment(payload=payload, db=db)


@router.post("/webhook/snippe")
async def snippe_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    raw_body = await request.body()
    handle_snippe_webhook(raw_body=raw_body, headers=request.headers, db=db)
    return {"status": "accepted"}


@router.post("/webhook/mixx")
async def mixx_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    raw_body = await request.body()
    return handle_mixx_webhook(raw_body=raw_body, headers=request.headers, db=db)
