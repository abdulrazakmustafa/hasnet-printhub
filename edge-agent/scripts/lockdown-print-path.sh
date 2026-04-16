#!/usr/bin/env bash
set -euo pipefail

CUPSD_SERVICE="cups"
ENABLE_UFW="0"
ALLOW_SSH_CIDR=""
DISABLE_AVAHI="1"

usage() {
  cat <<'USAGE'
Lock down Raspberry Pi print path so only the Pi can submit jobs to CUPS.

Usage:
  sudo ./lockdown-print-path.sh [options]

Options:
  --enable-ufw <0|1>       Enable UFW and block inbound IPP (default: 0)
  --allow-ssh-cidr <cidr>  Optional CIDR allowed for SSH when UFW is enabled
  --disable-avahi <0|1>    Stop mDNS advertisements from Pi (default: 1)
  -h, --help               Show this message
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable-ufw)
      ENABLE_UFW="$2"
      shift 2
      ;;
    --allow-ssh-cidr)
      ALLOW_SSH_CIDR="$2"
      shift 2
      ;;
    --disable-avahi)
      DISABLE_AVAHI="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$EUID" -ne 0 ]]; then
  echo "Run this script with sudo/root privileges." >&2
  exit 1
fi

if ! command -v cupsctl >/dev/null 2>&1; then
  echo "cupsctl command not found. Install CUPS first." >&2
  exit 1
fi

if ! command -v lpstat >/dev/null 2>&1; then
  echo "lpstat command not found. Install CUPS client tools first." >&2
  exit 1
fi

echo "[1/4] Restricting CUPS to local host only..."
cupsctl --no-remote-admin --no-remote-any --no-share-printers

echo "[2/4] Marking all configured printers as non-shared..."
while IFS= read -r printer_name; do
  [[ -z "$printer_name" ]] && continue
  lpadmin -p "$printer_name" -o printer-is-shared=false >/dev/null 2>&1 || true
done < <(lpstat -p 2>/dev/null | awk '/^printer / {print $2}')

echo "[3/4] Restarting CUPS..."
systemctl restart "$CUPSD_SERVICE"

if [[ "$DISABLE_AVAHI" == "1" ]]; then
  echo "[4/4] Disabling avahi advertisement from Pi..."
  systemctl disable --now avahi-daemon avahi-daemon.socket >/dev/null 2>&1 || true
else
  echo "[4/4] Skipping avahi change."
fi

if [[ "$ENABLE_UFW" == "1" ]]; then
  echo "[extra] Applying firewall rules..."
  if ! command -v ufw >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt update
    DEBIAN_FRONTEND=noninteractive apt install -y ufw
  fi

  if [[ -n "$ALLOW_SSH_CIDR" ]]; then
    ufw allow from "$ALLOW_SSH_CIDR" to any port 22 proto tcp >/dev/null
  else
    ufw allow 22/tcp >/dev/null
  fi
  ufw deny 631/tcp >/dev/null
  ufw deny 5353/udp >/dev/null
  ufw --force enable >/dev/null
fi

echo
echo "Lock-down complete."
echo "- CUPS remote admin: disabled"
echo "- CUPS printer sharing: disabled"
echo "- Direct IPP to Pi from kiosk LAN: blocked when UFW is enabled"
echo
echo "Important:"
echo "1) Put the printer on an operator-only SSID/VLAN (not kiosk user SSID)."
echo "2) Disable Wi-Fi Direct / hotspot mode on the printer."
echo "3) Keep users on a separate SSID/VLAN that cannot route to printer IP."
