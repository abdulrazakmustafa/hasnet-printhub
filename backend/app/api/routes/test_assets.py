from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

router = APIRouter()

_ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets"
_PAYMENT_SUCCESS_FILE = _ASSETS_DIR / "payment-success-test.pdf"
_UPLOADS_DIR = _ASSETS_DIR / "uploads"


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


@router.get("/uploads/{file_name}")
def uploaded_pdf_asset(file_name: str) -> FileResponse:
    normalized = (file_name or "").strip()
    if not normalized or "/" in normalized or "\\" in normalized or ".." in normalized:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    if not normalized.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    file_path = _UPLOADS_DIR / normalized
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    return FileResponse(file_path, media_type="application/pdf", filename=normalized)
