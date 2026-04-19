from __future__ import annotations

import getpass
from pathlib import Path
import subprocess
from typing import Any

from fastapi import HTTPException, status


def _run_local_sudo(command: list[str], *, sudo_password: str, timeout_sec: int = 25) -> dict[str, Any]:
    if not sudo_password.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sudo_password is required to execute this action.",
        )
    full = ["sudo", "-S", "-p", ""] + command
    completed = subprocess.run(
        full,
        input=(sudo_password + "\n"),
        text=True,
        capture_output=True,
        timeout=timeout_sec,
        check=False,
    )
    return {
        "ok": completed.returncode == 0,
        "code": int(completed.returncode),
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
    }


def _resolve_hotspot_script_path() -> str:
    user = getpass.getuser()
    candidates = [
        Path(f"/home/{user}/hasnet-printhub/edge-agent/scripts/configure-hotspot-ap.sh"),
        Path(f"/home/{user}/edge-agent/scripts/configure-hotspot-ap.sh"),
        Path("/home/hasnet_pi/hasnet-printhub/edge-agent/scripts/configure-hotspot-ap.sh"),
        Path("/home/hasnet_pi/edge-agent/scripts/configure-hotspot-ap.sh"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Hotspot setup script not found on device. Re-run edge-agent bootstrap first.",
    )


def _apply_hotspot_config(*, sudo_password: str, hotspot_config: dict[str, Any] | None) -> dict[str, Any]:
    config = hotspot_config or {}
    ssid = str(config.get("ssid") or "").strip()
    if not ssid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Hotspot SSID is required. Set it in admin Kiosk Controls first.",
        )

    security = str(config.get("wifi_security") or "WPA").strip().upper()
    if security not in {"WPA", "NOPASS"}:
        security = "WPA"
    passphrase = str(config.get("passphrase") or "").strip()
    if security == "WPA" and (len(passphrase) < 8 or len(passphrase) > 63):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Hotspot passphrase must be 8-63 characters for WPA mode.",
        )

    script_path = _resolve_hotspot_script_path()
    command = [
        script_path,
        "--interface",
        str(config.get("interface") or "wlan0").strip() or "wlan0",
        "--ssid",
        ssid,
        "--security",
        security,
        "--country",
        str(config.get("country") or "TZ").strip().upper() or "TZ",
        "--channel",
        str(config.get("channel") or 6).strip() if isinstance(config.get("channel"), str) else str(config.get("channel") or 6),
        "--gateway-ip",
        str(config.get("gateway_ip") or "10.55.0.1").strip() or "10.55.0.1",
        "--dhcp-start",
        str(config.get("dhcp_start") or "10.55.0.20").strip() or "10.55.0.20",
        "--dhcp-end",
        str(config.get("dhcp_end") or "10.55.0.220").strip() or "10.55.0.220",
    ]
    if security == "WPA":
        command.extend(["--passphrase", passphrase])
    return _run_local_sudo(command, sudo_password=sudo_password, timeout_sec=240)


def _disable_hotspot(*, sudo_password: str) -> dict[str, Any]:
    disable_script = """
set -e
systemctl stop hostapd dnsmasq || true
systemctl disable hostapd dnsmasq || true
rm -f /etc/dnsmasq.d/hph-kiosk-hotspot.conf
if [ -f /etc/dhcpcd.conf.hph-backup ]; then
  cp /etc/dhcpcd.conf.hph-backup /etc/dhcpcd.conf
else
  awk '
    BEGIN { skip = 0 }
    /# HPH_HOTSPOT_BEGIN/ { skip = 1; next }
    /# HPH_HOTSPOT_END/ { skip = 0; next }
    skip == 0 { print }
  ' /etc/dhcpcd.conf >/tmp/dhcpcd.conf.tmp && mv /tmp/dhcpcd.conf.tmp /etc/dhcpcd.conf
fi
systemctl restart dhcpcd || true
"""
    return _run_local_sudo(["bash", "-lc", disable_script], sudo_password=sudo_password, timeout_sec=120)


def execute_local_device_action(
    *,
    action: str,
    sudo_password: str,
    confirm_reboot: bool = False,
    hotspot_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = action.strip().lower()
    if normalized == "restart_agent":
        return _run_local_sudo(["systemctl", "restart", "hasnet-printhub-agent"], sudo_password=sudo_password)
    if normalized == "restart_api":
        return _run_local_sudo(["systemctl", "restart", "hasnet-printhub-api"], sudo_password=sudo_password)
    if normalized == "apply_hotspot":
        return _apply_hotspot_config(sudo_password=sudo_password, hotspot_config=hotspot_config)
    if normalized == "disable_hotspot":
        return _disable_hotspot(sudo_password=sudo_password)
    if normalized == "reboot_device":
        if not confirm_reboot:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="confirm_reboot=true is required before reboot_device action.",
            )
        return _run_local_sudo(["reboot"], sudo_password=sudo_password, timeout_sec=5)

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            "Unsupported action. Use restart_agent, restart_api, apply_hotspot, "
            "disable_hotspot, or reboot_device."
        ),
    )
