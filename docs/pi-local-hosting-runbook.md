# Pi-Local Hosting Runbook

Goal: run customer-facing flow fully on Raspberry Pi LAN, while keeping admin access remote-only.

## 1. Target Architecture

1. Backend API runs on Pi (`hasnet-printhub-api` systemd service).
2. PostgreSQL runs locally on Pi.
3. Edge agent runs on same Pi and calls local API (`127.0.0.1`).
4. Kiosk users access Pi over local intranet only.
5. Remote admin connects over secure tunnel/VPN (Tailscale or WireGuard).

## 2. Deploy Backend To Pi (Windows)

Run from project root:

```powershell
cd "C:\Users\Abdulrazak Mustafa\Documents\HPH\hasnet-printhub\backend"
powershell -ExecutionPolicy Bypass -File ".\scripts\bootstrap-backend-from-windows.ps1" `
  -PiHost "hph-pi01.local" `
  -PiUser "hasnet_pi" `
  -PostgresDb "hasnet_printhub" `
  -PostgresUser "hph" `
  -PostgresPassword "<strong-password>" `
  -BindHost "0.0.0.0" `
  -Port 8000
```

## 3. Point Edge Agent To Local Backend

On Pi:

```bash
sudo sed -i 's|^BACKEND_BASE_URL=.*|BACKEND_BASE_URL=http://127.0.0.1:8000/api/v1|' /home/hasnet_pi/edge-agent/.env
sudo systemctl restart hasnet-printhub-agent
```

## 4. Validate

On Pi:

```bash
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8000/api/v1/health
sudo systemctl status hasnet-printhub-api --no-pager
sudo systemctl status hasnet-printhub-agent --no-pager
```

## 5. Remote Admin Only

1. Do not expose public ports directly from Pi.
2. Use a private tunnel/VPN for admin endpoints.
3. Keep kiosk network separate from operator/admin network.

## 6. Payment Rule

No payment confirmation, no print:
- jobs dispatch only when `payment_status=confirmed`
- pending payments are reconciled by scheduler/manual reconcile endpoint
