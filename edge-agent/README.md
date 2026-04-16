# Edge Agent (Raspberry Pi Runtime)

This folder now contains a runnable Python edge agent for each kiosk device.

## Files

- `agent.py`: main loop (heartbeat + job polling).
- `config.py`: environment config loader.
- `monitor.py`: local printer/device health checks.
- `heartbeat.py`: sends `POST /api/v1/devices/heartbeat`.
- `job_runner.py`: fetches jobs and updates statuses.
- `systemd/hasnet-printhub-agent.service`: auto-start template for Raspberry Pi.

## Prototype Mode (No Printer Required)

1. Create virtual environment in this folder:
   - `python -m venv .venv`
2. Install deps:
   - `.venv\Scripts\pip install -r requirements.txt` (Windows)
   - `.venv/bin/pip install -r requirements.txt` (Linux/Pi)
3. Copy env file and edit:
   - `copy .env.example .env` (Windows)
   - `cp .env.example .env` (Linux/Pi)
4. Keep `MOCK_PRINT=true` for dry-run printing.
5. Start agent:
   - `.venv\Scripts\python agent.py` (Windows)
   - `.venv/bin/python agent.py` (Linux/Pi)

The agent will:
- heartbeat to backend,
- pull any paid jobs for `DEVICE_CODE`,
- simulate print, then mark them `printed`.

## One-Command Headless Bootstrap (Windows -> Pi)

After flashing Raspberry Pi OS Lite and enabling SSH, run from Windows PowerShell:

```powershell
cd C:\Users\Abdulrazak Mustafa\Documents\HPH\hasnet-printhub
.\edge-agent\scripts\bootstrap-from-windows.ps1 -PiHost hph-pi01.local -PiUser pi -BackendBaseUrl http://192.168.0.210:8000/api/v1 -DeviceCode pi-kiosk-001 -SiteName "Kiosk 1" -MockPrint $true
```

What this does:
- checks backend health and SSH connectivity,
- copies edge-agent files to `/home/<pi-user>/edge-agent`,
- writes `.env` using your passed values,
- installs Python runtime/dependencies on Pi,
- installs and starts `hasnet-printhub-agent` systemd service,
- tails recent service logs for quick validation.

Useful switches:
- `-NoSystemd` to skip service install and run manually.
- `-NoAvahi` to skip `avahi-daemon`.
- `-SkipBackendHealthCheck` if backend is intentionally offline.
- `-LockdownPrintPath` to lock CUPS to local Pi only after bootstrap.
- `-EnableUfwLockdown` to also block LAN IPP/mDNS on Pi firewall.
- `-AllowSshCidr "192.168.0.0/24"` to limit SSH source range when UFW is enabled.

## Real Printer Mode (Raspberry Pi + CUPS)

1. Install CUPS + drivers on Pi.
2. Set in `.env`:
   - `MOCK_PRINT=false`
   - `AUTO_DISCOVER_PRINTER=true` (recommended)
   - `PRINTER_NAME=<your-cups-printer-name>`
3. If backend returns relative `storage_key`, set:
   - `STORAGE_BASE_URL=https://<file-host-base-url>`

When `MOCK_PRINT=false`, the agent uses:
- `lpstat` to inspect printer status,
- `lp` to submit print jobs.
- blocks new dispatch while printer is not ready (`paper_out`, `paper_jam`, `paused`, etc.),
- retries download/print submission with backoff before marking a job failed.

Optional reliability tuning in `.env`:
- `RETRY_BACKOFF_SEC` (default `2`)
- `DOWNLOAD_RETRY_ATTEMPTS` (default `3`)
- `PRINT_SUBMIT_RETRY_ATTEMPTS` (default `3`)

## Wi-Fi Profile Provisioning (Move Sites Quickly)

Use script:
- `scripts/add-wifi-profile.sh`

Example on Pi:

```bash
cd ~/edge-agent
sudo ./scripts/add-wifi-profile.sh --ssid "SiteWifiName" --psk "SiteWifiPassword" --country TZ --priority 30
```

Notes:
- You can run this multiple times to save multiple sites.
- Higher `--priority` wins when multiple known networks are available.
- Script updates `/etc/wpa_supplicant/wpa_supplicant.conf` safely and reconfigures Wi-Fi.

## Printer Access Lock-Down (Prevent Payment Bypass)

Use script:
- `scripts/lockdown-print-path.sh`

Example on Pi:

```bash
cd ~/edge-agent
sudo ./scripts/lockdown-print-path.sh --enable-ufw 1 --allow-ssh-cidr "192.168.0.0/24"
```

What this enforces:
- CUPS remote admin disabled
- printer sharing disabled
- optional firewall block for inbound IPP (`631/tcp`) and mDNS (`5353/udp`) to Pi

Still required at network level:
- Put printer on operator-only SSID/VLAN (Pi + printer only).
- Keep kiosk users on a separate SSID/VLAN with no route to printer IP.
- Disable printer Wi-Fi Direct/hotspot mode.

## systemd Setup (Pi)

1. Copy project to `/home/pi/edge-agent`.
2. Copy service file:
   - `sudo cp systemd/hasnet-printhub-agent.service /etc/systemd/system/`
3. Enable and start:
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable hasnet-printhub-agent`
   - `sudo systemctl start hasnet-printhub-agent`
4. Check logs:
   - `journalctl -u hasnet-printhub-agent -f`
