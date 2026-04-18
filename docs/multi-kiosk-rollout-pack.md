# Multi-Kiosk Rollout Pack

Date: 2026-04-18

## 1) Goal

Clone the same Hasnet PrintHub behavior to new Raspberry Pi kiosks with:

1. Same backend + agent stack.
2. Per-kiosk profile values (host, device code, tokens, hotspot settings).
3. Per-kiosk QR entry URL for customer onboarding.

## 2) Profile-Driven Provisioning

Start from template:

`kiosk-profiles/template.kiosk-profile.json`

Create one local profile per kiosk (example):

`kiosk-profiles/kiosk-001.local.json`

Run preflight only (safe validation):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\provision-kiosk-from-profile.ps1 `
  -ProfilePath .\kiosk-profiles\kiosk-001.local.json `
  -ValidateOnly
```

Run actual provisioning:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\provision-kiosk-from-profile.ps1 `
  -ProfilePath .\kiosk-profiles\kiosk-001.local.json `
  -RunPostSmoke `
  -SmokeLimit 5
```

## 3) Hotspot Mode (Internet-Free Customer Access)

When `hotspot.enabled=true` in the kiosk profile, provisioning will configure Pi AP mode using:

`edge-agent/scripts/configure-hotspot-ap.sh`

Required hotspot profile keys:

1. `hotspot.ssid`
2. `hotspot.security` (`WPA` or `NOPASS`)
3. `hotspot.passphrase` (required for `WPA`)
4. `hotspot.gateway_ip` (default `10.55.0.1`)

Behavior:

1. Customer Wi-Fi QR connects phone to Pi hotspot.
2. Entry QR points to hotspot gateway (example `http://10.55.0.1:8000/customer-start`).
3. Customer flow works without public internet.

## 4) Per-Pi QR Pack Retrieval

Use admin API per device:

`GET /api/v1/admin/devices/{device_code}/qr-pack`

From Admin UI (`/admin-app`):

1. Open `Kiosk Controls` tab.
2. Set/confirm active device code.
3. Open `Per-Device QR Pack`.
4. Copy both:
   - Entry URL QR payload.
   - Wi-Fi QR payload.

Print both labels and attach to each kiosk.

## 5) Recommended Naming Standard

1. `device_code`: `pi-kiosk-001`, `pi-kiosk-002`, ...
2. hotspot SSID: `HPH-KIOSK-001`, `HPH-KIOSK-002`, ...
3. profile files: `kiosk-001.local.json`, `kiosk-002.local.json`, ...

## 6) Post-Clone Verification

1. `healthz` is OK.
2. Agent heartbeat updates `device.status=online`.
3. Printer status is `ready`.
4. Customer flow:
   - upload
   - quote
   - pay
   - printed
5. Admin panel shows payer info and payment lifecycle states.
