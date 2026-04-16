from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.payment_gateway import sync_pending_payments

router = APIRouter()


@router.get("/devices")
def admin_devices() -> dict[str, list]:
    return {"items": []}


@router.post("/payments/reconcile")
def admin_reconcile_payments(
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    synced = sync_pending_payments(db, limit=limit)
    return {"status": "ok", "synced": synced, "limit": limit}
