import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.api.routes.print_jobs import _UPLOADS_DIR, create_quote
from app.models.print_job import PrintJob
from app.schemas.print_job import PrintJobCreateRequest


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


def _write_upload(upload_id: str, file_name: str, content: bytes) -> tuple[Path, Path]:
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = _UPLOADS_DIR / f"{upload_id}.pdf"
    meta_path = _UPLOADS_DIR / f"{upload_id}.json"
    sha = hashlib.sha256(content).hexdigest()
    pdf_path.write_bytes(content)
    meta_path.write_text(
        json.dumps(
            {
                "upload_id": upload_id,
                "file_name": file_name,
                "file_size_bytes": len(content),
                "sha256": sha,
            }
        ),
        encoding="utf-8",
    )
    return pdf_path, meta_path


def test_create_quote_uses_upload_id_metadata() -> None:
    upload_id = str(uuid.uuid4())
    content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    pdf_path, meta_path = _write_upload(upload_id, "customer-doc.pdf", content)
    expected_sha = hashlib.sha256(content).hexdigest()

    try:
        payload = PrintJobCreateRequest(
            pages=2,
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
