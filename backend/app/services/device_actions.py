from __future__ import annotations

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


def execute_local_device_action(*, action: str, sudo_password: str, confirm_reboot: bool = False) -> dict[str, Any]:
    normalized = action.strip().lower()
    if normalized == "restart_agent":
        return _run_local_sudo(["systemctl", "restart", "hasnet-printhub-agent"], sudo_password=sudo_password)
    if normalized == "restart_api":
        return _run_local_sudo(["systemctl", "restart", "hasnet-printhub-api"], sudo_password=sudo_password)
    if normalized == "reboot_device":
        if not confirm_reboot:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="confirm_reboot=true is required before reboot_device action.",
            )
        return _run_local_sudo(["reboot"], sudo_password=sudo_password, timeout_sec=5)

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Unsupported action. Use restart_agent, restart_api, or reboot_device.",
    )

