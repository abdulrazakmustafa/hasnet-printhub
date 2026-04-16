from fastapi import APIRouter

router = APIRouter()


@router.get("/devices")
def admin_devices() -> dict[str, list]:
    return {"items": []}

