from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

_UPLOAD_ID_RE = re.compile(r"(?P<upload_id>[0-9a-fA-F-]{36})\.pdf$")

UPLOADS_DIR = Path(__file__).resolve().parents[2] / "assets" / "uploads"
UPLOAD_META_SUFFIX = ".json"


def upload_file_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}.pdf"


def upload_meta_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}{UPLOAD_META_SUFFIX}"


def parse_upload_id_from_storage_key(storage_key: str | None) -> str | None:
    if not storage_key:
        return None
    normalized = storage_key.strip().split("?")[0].split("#")[0]
    match = _UPLOAD_ID_RE.search(normalized)
    if not match:
        return None
    return match.group("upload_id").lower()


def delete_upload_artifacts(upload_id: str) -> dict[str, bool]:
    removed = {"pdf": False, "meta": False}
    pdf_path = upload_file_path(upload_id)
    if pdf_path.exists():
        pdf_path.unlink(missing_ok=True)
        removed["pdf"] = True

    meta_path = upload_meta_path(upload_id)
    if meta_path.exists():
        meta_path.unlink(missing_ok=True)
        removed["meta"] = True
    return removed


def cleanup_stale_upload_artifacts(*, max_age_hours: int, now_utc: datetime | None = None) -> dict[str, int]:
    safe_hours = min(max(int(max_age_hours), 1), 24 * 30)
    now = now_utc or datetime.now(timezone.utc)
    threshold = now - timedelta(hours=safe_hours)
    stats = {"pdf_removed": 0, "meta_removed": 0}

    if not UPLOADS_DIR.exists():
        return stats

    for path in UPLOADS_DIR.glob("*.pdf"):
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if modified >= threshold:
            continue
        path.unlink(missing_ok=True)
        stats["pdf_removed"] += 1

        upload_id = path.stem
        meta = upload_meta_path(upload_id)
        if meta.exists():
            meta.unlink(missing_ok=True)
            stats["meta_removed"] += 1

    return stats
