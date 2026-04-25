from __future__ import annotations

from datetime import datetime, timezone

import requests

from config import AgentSettings
from monitor import DeviceSnapshot


def _auth_headers(settings: AgentSettings) -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.api_token:
        headers["Authorization"] = f"Bearer {settings.api_token}"
    return headers


def send_heartbeat(
    session: requests.Session,
    settings: AgentSettings,
    snapshot: DeviceSnapshot,
) -> dict:
    payload = {
        "device_code": settings.device_code,
        "status": snapshot.status,
        "printer_status": snapshot.printer_status,
        "printer_name": snapshot.printer_name,
        "printer_details": snapshot.details,
        "paper_level_pct": snapshot.paper_level_pct,
        "toner_level_pct": snapshot.toner_level_pct,
        "ink_level_pct": snapshot.ink_level_pct,
        "active_error": snapshot.active_error,
        "uptime_seconds": snapshot.uptime_seconds,
        "boot_started_at": snapshot.boot_started_at,
        "local_ip": snapshot.local_ip,
        "public_ip": None,
        "site_name": settings.site_name,
        "agent_version": settings.agent_version,
        "firmware_version": settings.firmware_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    response = session.post(
        f"{settings.backend_base_url}/devices/heartbeat",
        json=payload,
        headers=_auth_headers(settings),
        timeout=settings.request_timeout_sec,
    )
    response.raise_for_status()
    parsed = response.json()
    if not isinstance(parsed, dict):
        return {"status": "unexpected_response"}
    return parsed
