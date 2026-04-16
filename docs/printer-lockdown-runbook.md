# Printer Lockdown Runbook (No Payment, No Print)

Goal: users must never reach the printer directly.  
Only Raspberry Pi can submit print jobs after backend payment confirmation.

## 1. Network Topology

1. Create operator network (`HPH-OPS`) for Pi + printer only.
2. Create kiosk network (`HPH-KIOSK`) for customer devices.
3. On router/firewall, block traffic from `HPH-KIOSK` to printer IP and Pi IPP port `631`.
4. Keep internet access policy:
   - Pi: internet allowed (payment provider/callback sync).
   - Kiosk users: local intranet only.

## 2. Printer Settings

1. Disable Wi-Fi Direct / hotspot mode on printer.
2. Disable cloud/email print features you do not use.
3. Set a printer admin password.

## 3. Pi CUPS Lockdown

Run on Pi:

```bash
cd ~/edge-agent
sudo ./scripts/lockdown-print-path.sh --enable-ufw 1 --allow-ssh-cidr "192.168.0.0/24"
```

This does:
- disables remote CUPS admin
- disables printer sharing
- blocks inbound IPP/mDNS to Pi when UFW enabled

## 4. Verify

Run on Pi:

```bash
cupsctl
lpstat -p -l
sudo ufw status verbose
```

Expected:
- remote admin is disabled
- printers are non-shared
- firewall denies `631/tcp`

## 5. Payment Gate Reminder

Backend must only dispatch jobs with `payment_status=confirmed`.
Pending/failed/expired payments must never be dispatched.
