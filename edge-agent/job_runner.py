from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

from config import AgentSettings
from monitor import can_accept_jobs, read_device_snapshot, resolve_printer_name

logger = logging.getLogger(__name__)
_BLOCKED_LOG_INTERVAL_SEC = 60
_last_blocked_log_at = 0.0
_last_blocked_status = ""


def _auth_headers(settings: AgentSettings) -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.api_token:
        headers["Authorization"] = f"Bearer {settings.api_token}"
    return headers


def _compact_text(value: str, *, limit: int = 220) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _log_blocked_printer_once(printer_status: str, details: str) -> None:
    global _last_blocked_log_at
    global _last_blocked_status

    now = time.time()
    if printer_status == _last_blocked_status and (now - _last_blocked_log_at) < _BLOCKED_LOG_INTERVAL_SEC:
        return
    _last_blocked_status = printer_status
    _last_blocked_log_at = now
    logger.warning(
        "Skipping fetch: printer not ready (%s). %s",
        printer_status,
        _compact_text(details, limit=160),
    )


def fetch_next_job(session: requests.Session, settings: AgentSettings) -> dict | None:
    response = session.get(
        f"{settings.backend_base_url}/devices/{settings.device_code}/next-job",
        headers=_auth_headers(settings),
        timeout=settings.request_timeout_sec,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return None
    if payload.get("status") != "assigned":
        return None
    return payload


def post_job_status(
    session: requests.Session,
    settings: AgentSettings,
    *,
    job_id: str,
    status: str,
    failure_reason: str | None = None,
) -> None:
    payload = {"status": status, "failure_reason": failure_reason}
    response = session.post(
        f"{settings.backend_base_url}/devices/{settings.device_code}/jobs/{job_id}/status",
        json=payload,
        headers=_auth_headers(settings),
        timeout=settings.request_timeout_sec,
    )
    response.raise_for_status()


def _download_job_pdf(
    session: requests.Session,
    settings: AgentSettings,
    *,
    job_id: str,
    storage_key: str,
) -> Path:
    if storage_key.startswith("http://") or storage_key.startswith("https://"):
        source_url = storage_key
    elif settings.storage_base_url:
        source_url = urljoin(f"{settings.storage_base_url}/", storage_key.lstrip("/"))
    else:
        raise RuntimeError("No downloadable URL for storage_key. Set STORAGE_BASE_URL or return full URL.")

    out_path = settings.spool_dir / f"{job_id}.pdf"
    with session.get(source_url, stream=True, timeout=settings.request_timeout_sec) as response:
        response.raise_for_status()
        with out_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("Downloaded file is empty.")
    return out_path


def _download_job_pdf_with_retry(
    session: requests.Session,
    settings: AgentSettings,
    *,
    job_id: str,
    storage_key: str,
) -> Path:
    last_error = ""
    for attempt in range(1, settings.download_retry_attempts + 1):
        try:
            return _download_job_pdf(session, settings, job_id=job_id, storage_key=storage_key)
        except Exception as exc:  # requests/http parsing/runtime URL issues
            last_error = str(exc)
            # Missing URL config is not transient; fail fast.
            if "No downloadable URL for storage_key" in last_error:
                break
            if attempt < settings.download_retry_attempts:
                logger.warning(
                    "Download retry %s/%s for job %s: %s",
                    attempt,
                    settings.download_retry_attempts,
                    job_id,
                    _compact_text(last_error),
                )
                time.sleep(settings.retry_backoff_sec * attempt)
    raise RuntimeError(
        f"Download failed after {settings.download_retry_attempts} attempt(s): {_compact_text(last_error)}"
    )


def _submit_to_cups(settings: AgentSettings, file_path: Path) -> None:
    target_printer = resolve_printer_name(settings)
    if not target_printer:
        raise RuntimeError("No printer configured or discovered. Set PRINTER_NAME or enable auto-discovery.")

    cmd = [settings.cups_lp_path]
    cmd.extend(["-d", target_printer])
    cmd.append(str(file_path))

    result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or f"lp exit code {result.returncode}"
        raise RuntimeError(detail)


def _submit_to_cups_with_retry(settings: AgentSettings, *, file_path: Path, job_id: str) -> None:
    last_error = ""
    for attempt in range(1, settings.print_submit_retry_attempts + 1):
        snapshot = read_device_snapshot(settings)
        if not can_accept_jobs(snapshot):
            last_error = f"Printer not ready ({snapshot.printer_status}). {snapshot.details}"
        else:
            try:
                _submit_to_cups(settings, file_path)
                return
            except RuntimeError as exc:
                last_error = str(exc)

        if attempt < settings.print_submit_retry_attempts:
            logger.warning(
                "Print submit retry %s/%s for job %s: %s",
                attempt,
                settings.print_submit_retry_attempts,
                job_id,
                _compact_text(last_error),
            )
            time.sleep(settings.retry_backoff_sec * attempt)

    raise RuntimeError(
        f"Print submit failed after {settings.print_submit_retry_attempts} attempt(s): {_compact_text(last_error)}"
    )


def process_one_job(session: requests.Session, settings: AgentSettings) -> bool:
    if not settings.mock_print:
        snapshot = read_device_snapshot(settings)
        if not can_accept_jobs(snapshot):
            _log_blocked_printer_once(snapshot.printer_status, snapshot.details)
            return False

    job = fetch_next_job(session, settings)
    if not job:
        return False

    job_id = str(job.get("job_id") or "").strip()
    storage_key = str(job.get("storage_key") or "").strip()
    if not job_id:
        logger.warning("Assigned job response missing job_id: %s", job)
        return False

    post_job_status(session, settings, job_id=job_id, status="printing")
    try:
        if settings.mock_print:
            time.sleep(settings.simulate_print_seconds)
        else:
            file_path = _download_job_pdf_with_retry(
                session,
                settings,
                job_id=job_id,
                storage_key=storage_key,
            )
            try:
                _submit_to_cups_with_retry(settings, file_path=file_path, job_id=job_id)
            finally:
                file_path.unlink(missing_ok=True)
        post_job_status(session, settings, job_id=job_id, status="printed")
        logger.info("Job %s completed.", job_id)
    except Exception as exc:
        failure_reason = _compact_text(str(exc), limit=400)
        try:
            post_job_status(session, settings, job_id=job_id, status="failed", failure_reason=failure_reason)
        except requests.RequestException as report_exc:
            logger.warning("Unable to report failed status for job %s: %s", job_id, report_exc)
        logger.warning("Job %s failed: %s", job_id, failure_reason)
    return True
