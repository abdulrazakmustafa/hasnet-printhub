from __future__ import annotations

import argparse
import posixpath
import time
from pathlib import Path

import paramiko


def _run_cmd(
    client: paramiko.SSHClient,
    command: str,
    *,
    sudo_password: str | None = None,
) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, get_pty=True)
    if sudo_password is not None:
        stdin.write(f"{sudo_password}\n")
        stdin.flush()
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return exit_code, out, err


def _sftp_mkdir_p(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    current = ""
    for part in remote_dir.strip("/").split("/"):
        current = f"{current}/{part}" if current else f"/{part}"
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy kiosk API/customer-app hotfix to Raspberry Pi via SSH password auth.")
    parser.add_argument("--pi-host", required=True)
    parser.add_argument("--pi-user", default="hasnet_pi")
    parser.add_argument("--pi-password", required=True)
    parser.add_argument("--remote-backend-dir", default="")
    parser.add_argument("--api-port", type=int, default=8000)
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1]
    project_root = backend_dir.parent
    remote_backend_dir = args.remote_backend_dir or f"/home/{args.pi_user}/hasnet-printhub/backend"
    remote_project_dir = posixpath.dirname(remote_backend_dir.rstrip("/"))

    files_to_upload = [
        ("app/main.py", "app/main.py"),
        ("app/api/routes/admin.py", "app/api/routes/admin.py"),
        ("app/api/routes/admin_auth.py", "app/api/routes/admin_auth.py"),
        ("app/api/routes/alerts.py", "app/api/routes/alerts.py"),
        ("app/api/routes/devices.py", "app/api/routes/devices.py"),
        ("app/api/routes/print_jobs.py", "app/api/routes/print_jobs.py"),
        ("app/api/deps.py", "app/api/deps.py"),
        ("app/api/router.py", "app/api/router.py"),
        ("app/core/config.py", "app/core/config.py"),
        ("app/core/security.py", "app/core/security.py"),
        ("app/services/payment_gateway.py", "app/services/payment_gateway.py"),
        ("app/services/admin_auth.py", "app/services/admin_auth.py"),
        ("app/services/customer_experience.py", "app/services/customer_experience.py"),
        ("app/services/device_actions.py", "app/services/device_actions.py"),
        ("app/services/pricing_config.py", "app/services/pricing_config.py"),
        ("app/services/refund_workflow.py", "app/services/refund_workflow.py"),
        ("app/static/customer_app/index.html", "app/static/customer_app/index.html"),
        ("app/static/customer_app/app.js", "app/static/customer_app/app.js"),
        ("app/static/customer_app/styles.css", "app/static/customer_app/styles.css"),
        ("app/static/admin_app/index.html", "app/static/admin_app/index.html"),
        ("app/static/admin_app/app.js", "app/static/admin_app/app.js"),
        ("app/static/admin_app/styles.css", "app/static/admin_app/styles.css"),
        ("app/schemas/device.py", "app/schemas/device.py"),
        ("app/schemas/print_job.py", "app/schemas/print_job.py"),
        ("requirements.txt", "requirements.txt"),
    ]
    edge_files_to_upload = ["config.py", "heartbeat.py", "monitor.py"]
    edge_target_dirs = [
        posixpath.join(remote_project_dir, "edge-agent"),
        f"/home/{args.pi_user}/edge-agent",
    ]
    edge_hotspot_local = project_root / "edge-agent" / "scripts" / "configure-hotspot-ap.sh"

    for local_rel, _ in files_to_upload:
        local_path = backend_dir / local_rel
        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
    for local_rel in edge_files_to_upload:
        local_path = project_root / "edge-agent" / local_rel
        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
    if not edge_hotspot_local.exists():
        raise FileNotFoundError(f"Local file not found: {edge_hotspot_local}")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=args.pi_host,
        username=args.pi_user,
        password=args.pi_password,
        look_for_keys=False,
        allow_agent=False,
        timeout=15,
    )

    try:
        with client.open_sftp() as sftp:
            for local_rel, remote_rel in files_to_upload:
                local_path = str(backend_dir / local_rel)
                remote_path = posixpath.join(remote_backend_dir, remote_rel.replace("\\", "/"))
                remote_dir = posixpath.dirname(remote_path)
                _sftp_mkdir_p(sftp, remote_dir)
                print(f"Uploading {local_rel} -> {remote_path}")
                sftp.put(local_path, remote_path)

            for edge_dir in edge_target_dirs:
                edge_hotspot_remote = posixpath.join(edge_dir, "scripts", "configure-hotspot-ap.sh")
                _sftp_mkdir_p(sftp, posixpath.dirname(edge_hotspot_remote))
                print(f"Uploading edge-agent hotspot script -> {edge_hotspot_remote}")
                sftp.put(str(edge_hotspot_local), edge_hotspot_remote)
                for local_rel in edge_files_to_upload:
                    local_path = str(project_root / "edge-agent" / local_rel)
                    remote_path = posixpath.join(edge_dir, local_rel)
                    _sftp_mkdir_p(sftp, posixpath.dirname(remote_path))
                    print(f"Uploading edge-agent {local_rel} -> {remote_path}")
                    sftp.put(local_path, remote_path)

        install_cmd = (
            f"{remote_backend_dir}/.venv/bin/python -m pip install "
            f"-r {remote_backend_dir}/requirements.txt"
        )
        code, out, err = _run_cmd(client, install_cmd)
        if code != 0:
            raise RuntimeError(f"Dependency install failed (exit={code}). stdout={out!r} stderr={err!r}")

        restart_cmd = "sudo -S -p '' systemctl restart hasnet-printhub-api && sudo -S -p '' systemctl is-active hasnet-printhub-api"
        code, out, err = _run_cmd(client, restart_cmd, sudo_password=args.pi_password)
        if code != 0:
            raise RuntimeError(f"Service restart failed (exit={code}). stdout={out!r} stderr={err!r}")
        safe_out = out.replace(args.pi_password, "********")
        print("Service state:", safe_out.strip() or "(empty)")

        health_cmd = f"curl -sS http://127.0.0.1:{args.api_port}/api/v1/health"
        health_ok = False
        for attempt in range(1, 13):
            code, out, err = _run_cmd(client, health_cmd)
            if code == 0 and '"status":"ok"' in out:
                print(f"Health OK on attempt {attempt}: {out.strip()}")
                health_ok = True
                break
            print(f"Health attempt {attempt} failed (code={code}). Retrying...")
            time.sleep(2)
        if not health_ok:
            raise RuntimeError(f"Remote check failed: {health_cmd}\nstdout={out}\nstderr={err}")

        for edge_dir in edge_target_dirs:
            edge_hotspot_remote = posixpath.join(edge_dir, "scripts", "configure-hotspot-ap.sh")
            chmod_cmd = f"chmod +x {edge_hotspot_remote}"
            code, out, err = _run_cmd(client, chmod_cmd)
            if code != 0:
                raise RuntimeError(f"Failed to chmod hotspot script (exit={code}). stdout={out!r} stderr={err!r}")

        agent_restart_cmd = "sudo -S -p '' systemctl restart hasnet-printhub-agent && sudo -S -p '' systemctl is-active hasnet-printhub-agent"
        code, out, err = _run_cmd(client, agent_restart_cmd, sudo_password=args.pi_password)
        if code != 0:
            raise RuntimeError(f"Agent restart failed (exit={code}). stdout={out!r} stderr={err!r}")
        safe_agent_out = out.replace(args.pi_password, "********")
        print("Agent state:", safe_agent_out.strip() or "(empty)")

        checks = [
            f"curl -sS http://127.0.0.1:{args.api_port}/api/v1/admin/pricing",
            f"curl -sS -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{args.api_port}/customer-app/",
            f"curl -sS -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{args.api_port}/admin-app/",
        ]
        for cmd in checks:
            code, out, err = _run_cmd(client, cmd)
            if code != 0:
                raise RuntimeError(f"Remote check failed: {cmd}\nstdout={out}\nstderr={err}")
            print(f"Check OK: {cmd}\n{out.strip()}")
    finally:
        client.close()

    print("Deploy complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
