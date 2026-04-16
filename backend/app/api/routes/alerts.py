from fastapi import APIRouter

router = APIRouter()


@router.get("")
def list_alerts() -> dict[str, list]:
    return {"items": []}

