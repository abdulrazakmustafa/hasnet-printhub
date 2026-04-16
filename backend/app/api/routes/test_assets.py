from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

router = APIRouter()

_ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets"
_PAYMENT_SUCCESS_FILE = _ASSETS_DIR / "payment-success-test.pdf"


@router.get("/payment-success-test.pdf")
def payment_success_test_pdf() -> FileResponse:
    if not _PAYMENT_SUCCESS_FILE.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test PDF asset not found.",
        )
    return FileResponse(
        _PAYMENT_SUCCESS_FILE,
        media_type="application/pdf",
        filename="payment-success-test.pdf",
    )
