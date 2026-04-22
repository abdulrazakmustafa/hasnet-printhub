from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _read_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class AgentSettings:
    backend_base_url: str
    device_code: str
    api_token: str
    site_name: str
    heartbeat_interval_sec: int
    poll_interval_sec: int
    request_timeout_sec: int
    retry_backoff_sec: int
    download_retry_attempts: int
    print_submit_retry_attempts: int
    print_complete_timeout_sec: int
    print_complete_poll_interval_sec: int
    agent_version: str
    firmware_version: str
    mock_print: bool
    simulate_print_seconds: int
    auto_discover_printer: bool
    printer_name: str
    cups_lp_path: str
    cups_lpstat_path: str
    cups_lpinfo_path: str
    storage_base_url: str
    spool_dir: Path


def load_settings(base_dir: Path | None = None) -> AgentSettings:
    root = base_dir or Path(__file__).resolve().parent
    _read_dotenv(root / ".env")

    spool_dir = Path(os.getenv("AGENT_SPOOL_DIR", str(root / "spool"))).expanduser().resolve()
    spool_dir.mkdir(parents=True, exist_ok=True)

    backend_base_url = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
    device_code = os.getenv("DEVICE_CODE", "prototype-local").strip()
    if not device_code:
        device_code = "prototype-local"

    return AgentSettings(
        backend_base_url=backend_base_url,
        device_code=device_code,
        api_token=os.getenv("DEVICE_API_TOKEN", "").strip(),
        site_name=os.getenv("SITE_NAME", device_code).strip() or device_code,
        heartbeat_interval_sec=max(10, _as_int(os.getenv("HEARTBEAT_INTERVAL_SEC"), default=30)),
        poll_interval_sec=max(2, _as_int(os.getenv("POLL_INTERVAL_SEC"), default=6)),
        request_timeout_sec=max(3, _as_int(os.getenv("REQUEST_TIMEOUT_SEC"), default=10)),
        retry_backoff_sec=max(1, _as_int(os.getenv("RETRY_BACKOFF_SEC"), default=2)),
        download_retry_attempts=max(1, _as_int(os.getenv("DOWNLOAD_RETRY_ATTEMPTS"), default=3)),
        print_submit_retry_attempts=max(1, _as_int(os.getenv("PRINT_SUBMIT_RETRY_ATTEMPTS"), default=3)),
        print_complete_timeout_sec=max(30, _as_int(os.getenv("PRINT_COMPLETE_TIMEOUT_SEC"), default=300)),
        print_complete_poll_interval_sec=max(2, _as_int(os.getenv("PRINT_COMPLETE_POLL_INTERVAL_SEC"), default=5)),
        agent_version=os.getenv("AGENT_VERSION", "0.1.0").strip() or "0.1.0",
        firmware_version=os.getenv("FIRMWARE_VERSION", "unknown").strip() or "unknown",
        mock_print=_as_bool(os.getenv("MOCK_PRINT"), default=False),
        simulate_print_seconds=max(1, _as_int(os.getenv("SIMULATE_PRINT_SECONDS"), default=4)),
        auto_discover_printer=_as_bool(os.getenv("AUTO_DISCOVER_PRINTER"), default=True),
        printer_name=os.getenv("PRINTER_NAME", "").strip(),
        cups_lp_path=os.getenv("CUPS_LP_PATH", "lp").strip() or "lp",
        cups_lpstat_path=os.getenv("CUPS_LPSTAT_PATH", "lpstat").strip() or "lpstat",
        cups_lpinfo_path=os.getenv("CUPS_LPINFO_PATH", "lpinfo").strip() or "lpinfo",
        storage_base_url=os.getenv("STORAGE_BASE_URL", "").rstrip("/"),
        spool_dir=spool_dir,
    )
