from __future__ import annotations

import re
import socket
import subprocess
from dataclasses import dataclass

from config import AgentSettings


@dataclass(frozen=True)
class DeviceSnapshot:
    status: str
    printer_status: str
    local_ip: str | None
    details: str


_DEFAULT_DEST_RE = re.compile(r"system default destination:\s*(?P<name>[^\s]+)", re.IGNORECASE)


def detect_local_ip() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


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
    if settings.mock_print:
        return DeviceSnapshot(
            status="online",
            printer_status="ready",
            local_ip=local_ip,
            details="MOCK_PRINT=true",
        )

    resolved_printer = resolve_printer_name(settings)
    command = [settings.cups_lpstat_path, "-p"]
    if resolved_printer:
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
            local_ip=local_ip,
            details=f"Command not found: {settings.cups_lpstat_path}",
        )
    except subprocess.SubprocessError as exc:
        return DeviceSnapshot(
            status="degraded",
            printer_status="unknown",
            local_ip=local_ip,
            details=f"lpstat check failed: {exc}",
        )

    out = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0:
        return DeviceSnapshot(
            status="degraded",
            printer_status="unknown",
            local_ip=local_ip,
            details=out.strip() or f"lpstat exited with {result.returncode}",
        )

    details = out.strip() or "lpstat ok"
    if resolved_printer:
        details = f"printer={resolved_printer}; {details}"

    status, printer_status = _status_from_lpstat(out)
    return DeviceSnapshot(
        status=status,
        printer_status=printer_status,
        local_ip=local_ip,
        details=details,
    )


def can_accept_jobs(snapshot: DeviceSnapshot) -> bool:
    return snapshot.printer_status in {"ready", "printing"}
