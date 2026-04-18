from pathlib import Path
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from app.api.routes.test_assets import _UPLOADS_DIR
from app.core.config import settings
from app.main import app


def _pdf_bytes(size_padding: int = 0, pages: int = 1) -> bytes:
    page_objects = []
    for idx in range(max(1, pages)):
        page_objects.append(
            f"{idx + 3} 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
        )
    payload = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        f"2 0 obj\n<< /Type /Pages /Count {max(1, pages)} /Kids [{' '.join([f'{i + 3} 0 R' for i in range(max(1, pages))])}] >>\nendobj\n"
        f"{''.join(page_objects)}"
        "%%EOF\n"
    ).encode("utf-8")
    return payload + (b"A" * max(0, size_padding))


def test_upload_pdf_success_and_download(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_reconcile_enabled", False)

    uploaded_file_path: Path | None = None
    uploaded_meta_path: Path | None = None
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/print-jobs/upload",
            files={"file": ("invoice.pdf", _pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 201

        payload = response.json()
        assert payload["upload_id"]
        assert payload["file_name"] == "invoice.pdf"
        assert payload["content_type"] == "application/pdf"
        assert payload["file_size_bytes"] > 0
        assert len(payload["sha256"]) == 64
        assert payload["page_count"] == 1
        assert "/api/v1/test-assets/uploads/" in payload["storage_key"]

        upload_path = Path(urlparse(payload["storage_key"]).path)
        uploaded_file_path = _UPLOADS_DIR / upload_path.name
        uploaded_meta_path = _UPLOADS_DIR / f"{payload['upload_id']}.json"

        fetch_response = client.get(upload_path.as_posix())
        assert fetch_response.status_code == 200
        assert fetch_response.content.startswith(b"%PDF-")

    if uploaded_file_path and uploaded_file_path.exists():
        uploaded_file_path.unlink()
    if uploaded_meta_path and uploaded_meta_path.exists():
        uploaded_meta_path.unlink()


def test_upload_pdf_rejects_non_pdf_content_type(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_reconcile_enabled", False)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/print-jobs/upload",
            files={"file": ("invoice.pdf", _pdf_bytes(), "text/plain")},
        )

    assert response.status_code == 422
    assert "Only PDF uploads are supported" in response.text


def test_upload_pdf_rejects_non_pdf_payload(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_reconcile_enabled", False)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/print-jobs/upload",
            files={"file": ("invoice.pdf", b"hello world", "application/pdf")},
        )

    assert response.status_code == 422
    assert "Uploaded content is not a PDF" in response.text


def test_upload_pdf_rejects_payload_over_size_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_reconcile_enabled", False)
    monkeypatch.setattr(settings, "upload_max_mb", 1)

    oversized_payload = _pdf_bytes(size_padding=(1024 * 1024) + 5)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/print-jobs/upload",
            files={"file": ("big.pdf", oversized_payload, "application/pdf")},
        )

    assert response.status_code == 413
    assert "exceeds 1 MB limit" in response.text
