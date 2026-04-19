import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.api.routes import print_jobs as print_jobs_routes
from app.api.routes.print_jobs import create_quote
from app.models.print_job import PrintJob
from app.schemas.print_job import PrintJobCreateRequest
from app.services.upload_storage import UPLOADS_DIR


class _FakeQuery:
    def __init__(self, device):
        self._device = device

    def filter(self, *_args, **_kwargs):
        return self

    def one_or_none(self):
        return self._device


class _FakeDB:
    def __init__(self, device=None):
        self._device = device
        self.added = []

    def query(self, _model):
        return _FakeQuery(self._device)

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "device_code", None):
            self._device = obj

    def flush(self):
        return None

    def commit(self):
        return None

    def refresh(self, _obj):
        if getattr(_obj, "id", None) is None:
            _obj.id = uuid.uuid4()
        return None


def _write_upload(upload_id: str, file_name: str, content: bytes, *, page_count: int) -> tuple[Path, Path]:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = UPLOADS_DIR / f"{upload_id}.pdf"
    meta_path = UPLOADS_DIR / f"{upload_id}.json"
    sha = hashlib.sha256(content).hexdigest()
    pdf_path.write_bytes(content)
    meta_path.write_text(
        json.dumps(
            {
                "upload_id": upload_id,
                "file_name": file_name,
                "file_size_bytes": len(content),
                "sha256": sha,
                "page_count": page_count,
            }
        ),
        encoding="utf-8",
    )
    return pdf_path, meta_path


def _pdf_bytes(page_count: int) -> bytes:
    pages = max(1, page_count)
    page_refs = " ".join([f"{i + 3} 0 R" for i in range(pages)])
    page_objects = []
    for idx in range(pages):
        page_objects.append(f"{idx + 3} 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n")
    return (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        f"2 0 obj\n<< /Type /Pages /Count {pages} /Kids [{page_refs}] >>\nendobj\n"
        f"{''.join(page_objects)}"
        "%%EOF\n"
    ).encode("utf-8")


def test_create_quote_uses_upload_id_metadata() -> None:
    upload_id = str(uuid.uuid4())
    content = _pdf_bytes(page_count=2)
    pdf_path, meta_path = _write_upload(upload_id, "customer-doc.pdf", content, page_count=2)
    expected_sha = hashlib.sha256(content).hexdigest()

    try:
        payload = PrintJobCreateRequest(
            pages=99,
            copies=1,
            color="bw",
            upload_id=upload_id,
            bw_price_per_page=100,
            color_price_per_page=300,
            currency="TZS",
        )
        db = _FakeDB()
        request = SimpleNamespace(base_url="http://hph-pi01.local:8000/")
        response = create_quote(payload=payload, request=request, db=db)

        created_job = next(item for item in db.added if isinstance(item, PrintJob))
        assert created_job.original_file_name == "customer-doc.pdf"
        assert created_job.storage_key.endswith(f"/api/v1/test-assets/uploads/{upload_id}.pdf")
        assert created_job.file_size_bytes == len(content)
        assert created_job.file_sha256 == expected_sha
        assert created_job.pages == 2
        assert response.total_cost == 200.0
    finally:
        if pdf_path.exists():
            pdf_path.unlink()
        if meta_path.exists():
            meta_path.unlink()


def test_create_quote_rejects_missing_upload_id_file() -> None:
    payload = PrintJobCreateRequest(
        pages=2,
        copies=1,
        color="bw",
        upload_id=str(uuid.uuid4()),
        bw_price_per_page=100,
        color_price_per_page=300,
        currency="TZS",
    )
    db = _FakeDB()
    request = SimpleNamespace(base_url="http://hph-pi01.local:8000/")

    with pytest.raises(HTTPException) as exc:
        create_quote(payload=payload, request=request, db=db)

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "upload_id file was not found" in exc.value.detail


def test_create_quote_supports_custom_page_range_from_upload() -> None:
    upload_id = str(uuid.uuid4())
    content = _pdf_bytes(page_count=5)
    pdf_path, meta_path = _write_upload(upload_id, "chapter.pdf", content, page_count=5)

    try:
        payload = PrintJobCreateRequest(
            pages=1,
            copies=2,
            color="bw",
            page_selection="range",
            range_start_page=2,
            range_end_page=4,
            upload_id=upload_id,
            bw_price_per_page=100,
            color_price_per_page=300,
            currency="TZS",
        )
        db = _FakeDB()
        request = SimpleNamespace(base_url="http://hph-pi01.local:8000/")
        response = create_quote(payload=payload, request=request, db=db)

        created_job = next(item for item in db.added if isinstance(item, PrintJob))
        assert created_job.pages == 3
        assert response.total_cost == 600.0
    finally:
        if pdf_path.exists():
            pdf_path.unlink()
        if meta_path.exists():
            meta_path.unlink()


def test_create_quote_rejects_custom_page_range_outside_upload_pages() -> None:
    upload_id = str(uuid.uuid4())
    content = _pdf_bytes(page_count=3)
    pdf_path, meta_path = _write_upload(upload_id, "range.pdf", content, page_count=3)

    try:
        payload = PrintJobCreateRequest(
            pages=3,
            copies=1,
            color="bw",
            page_selection="range",
            range_start_page=2,
            range_end_page=5,
            upload_id=upload_id,
            bw_price_per_page=100,
            color_price_per_page=300,
            currency="TZS",
        )
        db = _FakeDB()
        request = SimpleNamespace(base_url="http://hph-pi01.local:8000/")

        with pytest.raises(HTTPException) as exc:
            create_quote(payload=payload, request=request, db=db)

        assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "exceeds document length" in exc.value.detail
    finally:
        if pdf_path.exists():
            pdf_path.unlink()
        if meta_path.exists():
            meta_path.unlink()


def test_create_quote_rejects_color_when_printer_capability_is_disabled(monkeypatch) -> None:
    def fake_config() -> dict:
        return {
            "active_device_code": "pi-kiosk-001",
            "printer_capabilities": {
                "default": {"color_enabled": False, "a3_enabled": False},
                "devices": {},
            },
        }

    monkeypatch.setattr(print_jobs_routes, "get_customer_experience_config", fake_config)

    payload = PrintJobCreateRequest(
        pages=2,
        copies=1,
        color="color",
        bw_price_per_page=100,
        color_price_per_page=300,
        currency="TZS",
    )
    db = _FakeDB()
    request = SimpleNamespace(base_url="http://hph-pi01.local:8000/")

    with pytest.raises(HTTPException) as exc:
        create_quote(payload=payload, request=request, db=db)

    assert exc.value.status_code == status.HTTP_409_CONFLICT
    assert "Color printing is not enabled" in exc.value.detail


def test_create_quote_rejects_a3_when_printer_capability_is_disabled(monkeypatch) -> None:
    def fake_config() -> dict:
        return {
            "active_device_code": "pi-kiosk-001",
            "printer_capabilities": {
                "default": {"color_enabled": True, "a3_enabled": False},
                "devices": {},
            },
        }

    monkeypatch.setattr(print_jobs_routes, "get_customer_experience_config", fake_config)

    payload = PrintJobCreateRequest(
        pages=2,
        copies=1,
        color="bw",
        paper_size="a3",
        bw_price_per_page=100,
        color_price_per_page=300,
        currency="TZS",
    )
    db = _FakeDB()
    request = SimpleNamespace(base_url="http://hph-pi01.local:8000/")

    with pytest.raises(HTTPException) as exc:
        create_quote(payload=payload, request=request, db=db)

    assert exc.value.status_code == status.HTTP_409_CONFLICT
    assert "A3 printing is not enabled" in exc.value.detail
