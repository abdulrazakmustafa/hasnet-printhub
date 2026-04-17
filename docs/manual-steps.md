# Manual Setup Steps (Operator Checklist)

This document lists every step you should do manually outside code.

## 1. Server Prerequisites

1. Provision a Linux VM (Ubuntu 22.04+ recommended) with static IP.
2. Install Docker and Docker Compose plugin.
3. Create DNS `A` records:
   - `api.hasnet.co.tz` -> backend server IP
   - `*.hasnet.co.tz` -> frontend/web gateway IP
4. Install reverse proxy (`Nginx` or `Traefik`) and configure TLS certificates.

### Shared Hosting Note (Hostinger Cloud/Shared)

- Shared/cloud hosting plans without root access usually cannot run Docker containers or long-running Python API services.
- Keep prototype testing on local machine + Raspberry Pi first, then move backend to a VPS/server when ready for live rollout.
- This project structure is upgrade-safe: you can keep the same codebase and move from prototype mode to VPS production later.

### Windows Local Development Recovery (Docker Desktop)

Use this when Docker Desktop is installed but the engine does not start.

1. Open **PowerShell as Administrator**.
2. Install/repair WSL support:
   - `wsl --install`
   - `wsl --update`
3. Restart Windows.
4. Start Docker Desktop normally (do not run it as Administrator).
5. Verify engine health:
   - `docker version`
   - `docker info`
6. Return to `backend/` and continue bootstrapping:
   - `docker compose up -d`
   - `alembic upgrade head`

## 2. Credentials and Secrets

1. Generate secure secrets:
   - `SECRET_KEY` for JWT
   - DB password
2. Choose payment provider and request credentials:
   - `PAYMENT_PROVIDER=mixx` (recommended for current rollout) or `PAYMENT_PROVIDER=snippe`.
   - For Mixx:
     - `MIXX_BASE_URL`
     - `MIXX_PAYMENT_PATH` (leave blank if provider uses root path)
     - `MIXX_API_KEY`
     - `MIXX_USER_ID`
     - `MIXX_BILLER_MSISDN`
   - For Snippe:
     - `SNIPPE_BASE_URL`
     - `SNIPPE_API_KEY`
     - `SNIPPE_API_SECRET`
     - `SNIPPE_WEBHOOK_SECRET`
3. Configure email provider (SMTP or SendGrid/Mailgun):
   - host, port, username, password, from-address.
4. Store all secrets in `.env` (never commit them).

## 3. Backend Bootstrapping

1. Open terminal in `backend/`.
2. Create virtual environment and install packages:
   - `python -m venv .venv`
   - `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Linux)
   - `pip install -r requirements.txt`
3. Copy `.env.example` to `.env`.
   - Keep payment reconciliation enabled for prototype reliability:
     - `PAYMENT_RECONCILE_ENABLED=true`
     - `PAYMENT_RECONCILE_INTERVAL_SECONDS=30`
4. Start Postgres:
   - `docker compose up -d`
5. Apply DB migration:
   - `alembic upgrade head`
6. Start API service:
   - `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### Pi-Local Backend Option (Recommended For Intranet Kiosk Mode)

Instead of keeping backend on Windows LAN, deploy backend directly on Pi:

1. From Windows:
   - `cd C:\Users\Abdulrazak Mustafa\Documents\HPH\hasnet-printhub\backend`
   - `powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap-backend-from-windows.ps1 -PiHost hph-pi01.local -PiUser hasnet_pi -PostgresPassword "<strong-password>"`
2. On Pi, point edge-agent to local backend:
   - `BACKEND_BASE_URL=http://127.0.0.1:8000/api/v1`
3. Restart services:
   - `sudo systemctl restart hasnet-printhub-api hasnet-printhub-agent`
4. Validate:
   - `curl http://127.0.0.1:8000/healthz`

## 4. Raspberry Pi Manual Setup

1. Flash Raspberry Pi OS Lite.
2. Enable SSH and secure with key auth.
3. Optional fast path from Windows (recommended for prototype):
   - `.\edge-agent\scripts\bootstrap-from-windows.ps1 -PiHost <pi-host-or-ip> -PiUser <pi-user> -BackendBaseUrl http://192.168.0.210:8000/api/v1 -DeviceCode pi-kiosk-001`
4. Install CUPS and printer drivers:
   - `sudo apt update && sudo apt install cups printer-driver-all`
5. Add `pi` user to `lpadmin`.
6. Configure printer via CUPS web UI (`http://localhost:631`).
7. Install edge-agent dependencies (`python3`, `pip`, `pycups`, `requests`).
8. Set device code and API token in edge-agent config.
9. Register device from admin endpoint.
10. Configure systemd service for auto-start and restart on failure.
11. Save additional Wi-Fi networks for multi-site operation:
   - `cd ~/edge-agent`
   - `sudo ./scripts/add-wifi-profile.sh --ssid "<site-ssid>" --psk "<site-password>" --country TZ --priority 30`
12. Lock down print path to prevent direct user printing:
   - `cd ~/edge-agent`
   - `sudo ./scripts/lockdown-print-path.sh --enable-ufw 1 --allow-ssh-cidr "<admin-cidr>"`
13. Separate networks:
   - Printer + Pi on operator-only SSID/VLAN.
   - Kiosk users on a different SSID/VLAN with no route to printer IP.
14. On printer settings panel:
   - disable Wi-Fi Direct / hotspot printing features.

## 5. Payment Webhook Manual Setup

1. Expose webhook URL over HTTPS:
   - Mixx: `https://api.hasnet.co.tz/api/v1/payments/webhook/mixx`
   - Snippe: `https://api.hasnet.co.tz/api/v1/payments/webhook/snippe`
2. Register the selected webhook URL with your payment provider.
3. Ensure backend `.env` has matching provider credentials.
4. Test with sandbox transaction before production go-live.

## 6. Email Alerting Manual Setup

1. Add maintenance/admin emails in database.
2. Configure SMTP credentials in `.env`.
3. Trigger test alert via API endpoint and verify inbox delivery.
4. Add fallback mailbox and spam whitelist rules.

## 7. Operations Checklist

1. Backup Postgres daily.
2. Rotate device API tokens periodically.
3. Rotate payment and SMTP credentials every 90 days.
4. Monitor uptime, queue depth, and failed jobs.
5. Keep a printer consumables replacement schedule per site.
6. For delayed payment incidents, follow `docs/payment-pending-operator-runbook.md`.
7. Use `backend/scripts/investigate-snippe-payment-via-ssh.ps1` (or `investigate-snippe-payment-on-pi.sh`) to capture consistent pending-payment evidence.
