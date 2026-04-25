# HP LaserJet Enterprise M506 + Pi Network Day-1 Guide
Date: April 25, 2026
Scope: Tomorrow setup checklist for Hasnet PrintHub kiosk Pi

## 1) What Is Already Configured in Your Codebase
1. Edge-agent defaults to real mode with `MOCK_PRINT=false` in `.env.example`.
2. `AUTO_DISCOVER_PRINTER=true` is supported and enabled by default in config.
3. Agent resolves printer from CUPS default destination or first available CUPS queue.
4. Agent checks USB/network printer URI reachability and reports online/offline status.

Important:
Auto-discovery here means "auto-pick an existing CUPS queue."
You still need CUPS and a printer queue configured at least once.

## 2) Tomorrow: Physical Connection Order
1. Power off printer and Pi.
2. Connect HP M506 to Pi using USB cable.
3. Connect Pi Ethernet (`eth0`) to router/switch for internet/backhaul.
4. Power on printer first, then Pi.
5. Wait 60 to 120 seconds.

## 3) Verify Printer Detection on Pi
SSH into Pi, then run:

```bash
lsusb
lpinfo -v | grep -Ei 'usb|hp|m506' || true
lpstat -p -d
```

Expected:
1. `lsusb` shows HP device.
2. `lpinfo -v` includes a USB URI.
3. `lpstat -p -d` shows an available/default printer queue.

If no queue exists yet, configure once:
1. Open `http://localhost:631` on Pi and add printer, or
2. Use `lpadmin` CLI with detected URI.

## 4) Ensure Agent Uses It
In `~/edge-agent/.env`:
1. Keep `MOCK_PRINT=false`.
2. Keep `AUTO_DISCOVER_PRINTER=true`.
3. Optional: set `PRINTER_NAME=<exact-cups-name>` to pin specific queue.

Then restart:

```bash
sudo systemctl restart hasnet-printhub-agent
sudo journalctl -u hasnet-printhub-agent -n 120 --no-pager
```

## 5) Ethernet Auto-Connect Expectation
For Raspberry Pi OS, Ethernet on `eth0` usually gets DHCP automatically once cable/router are active.

Check:

```bash
ip -br addr show eth0
ip route
ping -c 3 8.8.8.8
```

If no IP on `eth0`, troubleshoot router DHCP/cable/port first.

## 6) Change Wi-Fi Network on Pi (Fast Method)
Your repo already has:
`edge-agent/scripts/add-wifi-profile.sh`

On Pi:

```bash
cd ~/edge-agent
sudo ./scripts/add-wifi-profile.sh --ssid "NEW_WIFI_NAME" --psk "NEW_WIFI_PASSWORD" --country TZ --priority 30
```

Then verify:

```bash
wpa_cli -i wlan0 list_networks
ip -br addr show wlan0
```

## 7) If You Want Me To Connect It For You
Yes, I can do it remotely from this workspace if you provide:
1. Pi host/IP.
2. SSH username.
3. SSH password (or key path available here).
4. Wi-Fi SSID and password.

Then I can run the exact command safely and confirm connectivity logs for you.

## 8) Quick Troubleshooting
1. Agent says no printer:
   - Check `lpstat -p -d`.
   - Ensure CUPS queue exists and printer is enabled.
2. USB seen but still offline:
   - Replug USB cable and power-cycle printer.
   - Recheck `lpinfo -v` and `lpstat -p -l`.
3. Ethernet connected but no internet:
   - Confirm router DHCP and upstream internet.
   - Try another cable/port.
4. Wi-Fi profile saved but not connecting:
   - Re-run command with exact SSID/password (case-sensitive).
   - Reboot Pi if needed.

## 9) Suggested Day-1 Acceptance Test
1. Printer visible in CUPS and reports `idle`/`ready`.
2. Agent heartbeat visible in admin dashboard.
3. One paid test job prints end-to-end.
4. Customer status changes to printed.
5. Receipt and payment trace available in admin records.
