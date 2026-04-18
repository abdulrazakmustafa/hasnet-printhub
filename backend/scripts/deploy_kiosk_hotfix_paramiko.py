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
    remote_backend_dir = args.remote_backend_dir or f"/home/{args.pi_user}/hasnet-printhub/backend"

    files_to_upload = [
        ("app/main.py", "app/main.py"),
        ("assets/logo-white-2.png", "assets/logo-white-2.png"),
        ("app/api/routes/print_jobs.py", "app/api/routes/print_jobs.py"),
        ("app/api/routes/devices.py", "app/api/routes/devices.py"),
        ("app/core/config.py", "app/core/config.py"),
        ("app/services/upload_storage.py", "app/services/upload_storage.py"),
        ("app/static/customer_app/index.html", "app/static/customer_app/index.html"),
        ("app/static/customer_app/app.js", "app/static/customer_app/app.js"),
        ("app/static/customer_app/styles.css", "app/static/customer_app/styles.css"),
        ("app/schemas/print_job.py", "app/schemas/print_job.py"),
    ]

    for local_rel, _ in files_to_upload:
        local_path = backend_dir / local_rel
        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")

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
