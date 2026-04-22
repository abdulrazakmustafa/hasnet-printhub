# Multi-Pi Quickstart (One Admin Backend)

Use this when adding more kiosks (Pi devices) to the same Hasnet admin system.

## 1. Prepare one profile per Pi

1. Copy:
`scripts/profiles/kiosk-template.json`
2. Rename for each kiosk, for example:
`scripts/profiles/kiosk-002.json`
3. Update at minimum:
- `pi.host`
- `agent.backend_base_url` (same central admin backend for all kiosks)
- `agent.device_code` (must be unique per Pi)
- `agent.device_api_token`
- `agent.site_name`
- `hotspot.ssid`

## 2. Provision each Pi

Run from repo root on Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\provision-kiosk-from-profile.ps1 `
  -ProfilePath .\scripts\profiles\kiosk-002.json `
  -SkipBackend `
  -RunPostSmoke `
  -SmokeLimit 5
```

Notes:
- `-SkipBackend` keeps one shared admin backend (recommended for multi-kiosk).
- The script installs/updates edge-agent, writes `.env`, enables `hasnet-printhub-agent`, and applies hotspot when enabled in profile.

## 3. Validate in admin panel

After provisioning, kiosk appears automatically on first heartbeat:
- Admin -> `Kiosks & Printers`
- Device scope selector in top bar

If it does not appear:

```bash
sudo systemctl status hasnet-printhub-agent --no-pager
sudo journalctl -u hasnet-printhub-agent -n 120 --no-pager
```

