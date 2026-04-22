from __future__ import annotations

import re
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from config import AgentSettings


@dataclass(frozen=True)
class DeviceSnapshot:
    status: str
    printer_status: str
    printer_name: str | None
    local_ip: str | None
    details: str
    active_error: str | None
    uptime_seconds: int | None
    boot_started_at: str | None


_DEFAULT_DEST_RE = re.compile(r"system default destination:\s*(?P<name>[^\s]+)", re.IGNORECASE)
_DEVICE_FOR_RE = re.compile(r"device for (?P<name>[^:]+):\s*(?P<uri>\S+)", re.IGNORECASE)


def detect_local_ip() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def _read_uptime_seconds() -> int | None:
    try:
        raw = Path("/proc/uptime").read_text(encoding="utf-8").strip()
    except Exception:
        return None
    first = (raw.split() or [""])[0]
    try:
        parsed = int(float(first))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _boot_started_at_iso(uptime_seconds: int | None) -> str | None:
    if uptime_seconds is None:
        return None
    boot_at = datetime.now(timezone.utc).timestamp() - float(uptime_seconds)
    return datetime.fromtimestamp(boot_at, tz=timezone.utc).isoformat()


def _status_from_lpstat(output: str) -> tuple[str, str]:
    text = output.lower()
    if "paper" in text and ("out" in text or "empty" in text or "load paper" in text):
        return "degraded", "paper_out"
    if "jam" in text:
        return "degraded", "paper_jam"
    if "toner" in text and ("low" in text or "empty" in text):
        return "degraded", "low_toner"
    if "cover" in text and ("open" in text):
        return "degraded", "cover_open"
    if "queue" in text and ("stuck" in text or "stalled" in text):
        return "degraded", "queue_stuck"
    if "disabled" in text or "offline" in text:
        return "offline", "offline"
    if "printing" in text:
        return "online", "printing"
    if "paused" in text:
        return "degraded", "paused"
    if "error" in text:
        return "degraded", "error"
    if "idle" in text or "ready" in text:
        return "online", "ready"
    return "degraded", "unknown"


def _active_error_from_status(printer_status: str, details: str) -> str | None:
    if printer_status in {"ready", "printing"}:
        return None
    text = details.strip()
    if not text:
        return f"printer_status={printer_status}"
    return f"{printer_status}: {text}"


def _extract_default_destination(output: str) -> str | None:
    match = _DEFAULT_DEST_RE.search(output)
    if not match:
        return None
    return (match.group("name") or "").strip() or None


def _extract_first_printer_name(output: str) -> str | None:
    for raw in output.splitlines():
        line = raw.strip()
        if not line.lower().startswith("printer "):
            continue
        parts = line.split()
        if len(parts) >= 2:
            return parts[1]
    return None


def _extract_printer_uri(output: str, *, printer_name: str | None = None) -> str | None:
    target = (printer_name or "").strip().lower()
    for raw in output.splitlines():
        line = raw.strip()
        match = _DEVICE_FOR_RE.search(line)
        if not match:
            continue
        name = (match.group("name") or "").strip().lower()
        uri = (match.group("uri") or "").strip()
        if not uri:
            continue
        if target and name != target:
            continue
        return uri
    return None


def _read_printer_uri(settings: AgentSettings, printer_name: str) -> str | None:
    if not printer_name:
        return None
    try:
        result = subprocess.run(
            [settings.cups_lpstat_path, "-v", printer_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    out = (result.stdout or "") + "\n" + (result.stderr or "")
    return _extract_printer_uri(out, printer_name=printer_name)


def _read_lpinfo_output(settings: AgentSettings) -> str:
    lpinfo_path = str(getattr(settings, "cups_lpinfo_path", "lpinfo") or "lpinfo")
    try:
        result = subprocess.run(
            [lpinfo_path, "-v"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return ((result.stdout or "") + "\n" + (result.stderr or "")).strip()


def _tcp_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _is_printer_uri_available(settings: AgentSettings, printer_uri: str) -> bool:
    uri = str(printer_uri or "").strip()
    if not uri:
        return False
    lowered = uri.lower()

    # Local USB/parallel/serial backends are only "connected" when lpinfo still reports the same URI.
    if lowered.startswith(("usb://", "serial:", "parallel:", "hp:/usb/", "hpfax:/usb/")):
        lpinfo = _read_lpinfo_output(settings).lower()
        return bool(lpinfo) and lowered in lpinfo

    parsed = urlparse(uri)
    scheme = (parsed.scheme or "").lower()
    if scheme in {"socket", "ipp", "ipps", "http", "https", "lpd"}:
        host = parsed.hostname
        if not host:
            return False
        port = parsed.port
        if port is None:
            if scheme == "socket":
                port = 9100
            elif scheme == "lpd":
                port = 515
            else:
                port = 631
        return _tcp_reachable(host, int(port))

    # Unknown backend: do not force-disconnect unless lpstat itself reports offline/error.
    return True


def resolve_printer_name(settings: AgentSettings) -> str | None:
    if settings.printer_name:
        return settings.printer_name
    if not settings.auto_discover_printer:
        return None

    try:
        default_result = subprocess.run(
            [settings.cups_lpstat_path, "-d"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        default_text = (default_result.stdout or "") + "\n" + (default_result.stderr or "")
        resolved = _extract_default_destination(default_text)
        if resolved:
            return resolved
    except subprocess.SubprocessError:
        pass

    try:
        printers_result = subprocess.run(
            [settings.cups_lpstat_path, "-p"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        printers_text = (printers_result.stdout or "") + "\n" + (printers_result.stderr or "")
        return _extract_first_printer_name(printers_text)
    except subprocess.SubprocessError:
        return None


def read_device_snapshot(settings: AgentSettings) -> DeviceSnapshot:
    local_ip = detect_local_ip()
    uptime_seconds = _read_uptime_seconds()
    boot_started_at = _boot_started_at_iso(uptime_seconds)
    if settings.mock_print:
        return DeviceSnapshot(
            status="degraded",
            printer_status="unknown",
            printer_name=settings.printer_name or "mock-printer",
            local_ip=local_ip,
            details="MOCK_PRINT=true (simulation mode; real printer telemetry disabled)",
            active_error="mock_mode_enabled",
            uptime_seconds=uptime_seconds,
            boot_started_at=boot_started_at,
        )

    resolved_printer = resolve_printer_name(settings)
    if not resolved_printer:
        return DeviceSnapshot(
            status="offline",
            printer_status="offline",
            printer_name=None,
            local_ip=local_ip,
            details="No printer is configured or discoverable from CUPS.",
            active_error="offline: no printer connected",
            uptime_seconds=uptime_seconds,
            boot_started_at=boot_started_at,
        )

    printer_uri = _read_printer_uri(settings, resolved_printer)
    printer_uri_available = _is_printer_uri_available(settings, printer_uri) if printer_uri else True
    command = [settings.cups_lpstat_path, "-p"]
    command.append(resolved_printer)
    command.append("-l")

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return DeviceSnapshot(
            status="degraded",
            printer_status="unknown",
            printer_name=resolved_printer,
            local_ip=local_ip,
            details=f"Command not found: {settings.cups_lpstat_path}",
            active_error=f"unknown: command not found ({settings.cups_lpstat_path})",
            uptime_seconds=uptime_seconds,
            boot_started_at=boot_started_at,
        )
    except subprocess.SubprocessError as exc:
        return DeviceSnapshot(
            status="degraded",
            printer_status="unknown",
            printer_name=resolved_printer,
            local_ip=local_ip,
            details=f"lpstat check failed: {exc}",
            active_error=f"unknown: lpstat check failed ({exc})",
            uptime_seconds=uptime_seconds,
            boot_started_at=boot_started_at,
        )

    out = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0:
        return DeviceSnapshot(
            status="degraded",
            printer_status="unknown",
            printer_name=resolved_printer,
            local_ip=local_ip,
            details=out.strip() or f"lpstat exited with {result.returncode}",
            active_error=f"unknown: {out.strip() or f'lpstat exited with {result.returncode}'}",
            uptime_seconds=uptime_seconds,
            boot_started_at=boot_started_at,
        )

    details = out.strip() or "lpstat ok"
    if resolved_printer:
        details = f"printer={resolved_printer}; {details}"
    if printer_uri:
        details = f"{details}; uri={printer_uri}"

    status, printer_status = _status_from_lpstat(out)
    if not printer_uri_available:
        status = "offline"
        printer_status = "offline"
        details = f"{details}; disconnected: printer URI is not reachable"
    return DeviceSnapshot(
        status=status,
        printer_status=printer_status,
        printer_name=resolved_printer,
        local_ip=local_ip,
        details=details,
        active_error=_active_error_from_status(printer_status, details),
        uptime_seconds=uptime_seconds,
        boot_started_at=boot_started_at,
    )


def can_accept_jobs(snapshot: DeviceSnapshot) -> bool:
    return snapshot.printer_status in {"ready", "printing"}
