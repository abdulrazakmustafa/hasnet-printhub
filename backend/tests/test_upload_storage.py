from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services import upload_storage


def _with_temp_upload_dir() -> tuple[Path, Path]:
    temp_root = Path(__file__).resolve().parent / "_tmp_upload_storage" / str(uuid.uuid4())
    temp_root.mkdir(parents=True, exist_ok=True)
    original_dir = upload_storage.UPLOADS_DIR
    upload_storage.UPLOADS_DIR = temp_root
    return temp_root, original_dir


def _restore_upload_dir(original_dir: Path, temp_root: Path) -> None:
    upload_storage.UPLOADS_DIR = original_dir
    shutil.rmtree(temp_root, ignore_errors=True)


def test_parse_upload_id_from_storage_key() -> None:
    upload_id = "cb113cf5-6d8a-40ec-945c-d72a8d2bbbd0"
    storage_key = f"http://hph-pi01.local:8000/api/v1/test-assets/uploads/{upload_id}.pdf?sig=abc#frag"

    parsed = upload_storage.parse_upload_id_from_storage_key(storage_key)

    assert parsed == upload_id


def test_delete_upload_artifacts_removes_pdf_and_meta() -> None:
    temp_root, original_dir = _with_temp_upload_dir()
    try:
        upload_id = "f2cb22c9-c0dc-4dc8-91d0-4f488ed57e58"
        pdf_path = upload_storage.upload_file_path(upload_id)
        meta_path = upload_storage.upload_meta_path(upload_id)
        pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n%%EOF")
        meta_path.write_text(json.dumps({"upload_id": upload_id}), encoding="utf-8")

        removed = upload_storage.delete_upload_artifacts(upload_id)

        assert removed == {"pdf": True, "meta": True}
        assert not pdf_path.exists()
        assert not meta_path.exists()
    finally:
        _restore_upload_dir(original_dir, temp_root)


def test_cleanup_stale_upload_artifacts_only_removes_old_files() -> None:
    temp_root, original_dir = _with_temp_upload_dir()
    try:
        stale_id = "3ad53557-5070-4ae5-8e22-6e2256a2484d"
        fresh_id = "ec0d2f22-3887-4a8d-911a-1ef6e6755e77"

        stale_pdf = upload_storage.upload_file_path(stale_id)
        stale_meta = upload_storage.upload_meta_path(stale_id)
        fresh_pdf = upload_storage.upload_file_path(fresh_id)
        fresh_meta = upload_storage.upload_meta_path(fresh_id)

        stale_pdf.write_bytes(b"%PDF-1.4\nstale")
        stale_meta.write_text("{}", encoding="utf-8")
        fresh_pdf.write_bytes(b"%PDF-1.4\nfresh")
        fresh_meta.write_text("{}", encoding="utf-8")

        now = datetime.now(timezone.utc)
        old_timestamp = (now - timedelta(hours=30)).timestamp()
        stale_pdf.touch()
        stale_meta.touch()
        fresh_pdf.touch()
        fresh_meta.touch()

        # Make stale upload older than cleanup threshold.
        os.utime(stale_pdf, (old_timestamp, old_timestamp))
        os.utime(stale_meta, (old_timestamp, old_timestamp))

        stats = upload_storage.cleanup_stale_upload_artifacts(max_age_hours=24, now_utc=now)

        assert stats == {"pdf_removed": 1, "meta_removed": 1}
        assert not stale_pdf.exists()
        assert not stale_meta.exists()
        assert fresh_pdf.exists()
        assert fresh_meta.exists()
    finally:
        _restore_upload_dir(original_dir, temp_root)
