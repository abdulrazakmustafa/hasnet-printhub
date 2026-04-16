#!/usr/bin/env bash
set -euo pipefail

SSID=""
PSK=""
COUNTRY="TZ"
PRIORITY="20"
INTERFACE="wlan0"
CONF_FILE="/etc/wpa_supplicant/wpa_supplicant.conf"

usage() {
  cat <<'USAGE'
Add or update a Wi-Fi profile for Raspberry Pi.

Usage:
  sudo ./add-wifi-profile.sh --ssid <name> --psk <password> [options]

Options:
  --ssid <name>           Wi-Fi SSID (required)
  --psk <password>        Wi-Fi password (required)
  --country <code>        Regulatory country code (default: TZ)
  --priority <num>        Network priority (default: 20)
  --interface <ifname>    Wireless interface for reconfigure (default: wlan0)
  --conf-file <path>      wpa_supplicant.conf path (default: /etc/wpa_supplicant/wpa_supplicant.conf)
  -h, --help              Show this message
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssid) SSID="${2:-}"; shift 2 ;;
    --psk) PSK="${2:-}"; shift 2 ;;
    --country) COUNTRY="${2:-}"; shift 2 ;;
    --priority) PRIORITY="${2:-}"; shift 2 ;;
    --interface) INTERFACE="${2:-}"; shift 2 ;;
    --conf-file) CONF_FILE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ "$EUID" -ne 0 ]]; then
  echo "Run with sudo/root." >&2
  exit 1
fi
if [[ -z "$SSID" || -z "$PSK" ]]; then
  echo "--ssid and --psk are required." >&2
  usage
  exit 1
fi
if ! command -v wpa_passphrase >/dev/null 2>&1; then
  echo "wpa_passphrase not found. Install wpasupplicant package first." >&2
  exit 1
fi

mkdir -p "$(dirname "$CONF_FILE")"
if [[ ! -f "$CONF_FILE" ]]; then
  cat > "$CONF_FILE" <<EOF
country=$COUNTRY
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
EOF
fi

TMP_BASE="$(mktemp)"
TMP_PROFILE="$(mktemp)"
trap 'rm -f "$TMP_BASE" "$TMP_PROFILE"' EXIT

# Remove existing block for same SSID, keep all others.
awk -v ssid="$SSID" '
BEGIN { in_block=0; block=""; keep=1 }
{
  if ($0 ~ /^network=\{/) {
    in_block=1
    block=$0 ORS
    keep=1
    next
  }

  if (in_block) {
    block=block $0 ORS
    if ($0 ~ "^[[:space:]]*ssid=\"" ssid "\"$") {
      keep=0
    }
    if ($0 ~ /^\}/) {
      if (keep) {
        printf "%s", block
      }
      in_block=0
      block=""
      keep=1
    }
    next
  }

  print
}
END {
  if (in_block && keep) {
    printf "%s", block
  }
}
' "$CONF_FILE" > "$TMP_BASE"

wpa_passphrase "$SSID" "$PSK" | sed '/^[[:space:]]*#psk=/d' > "$TMP_PROFILE"
sed -i "/^[[:space:]]*}/i\\    priority=$PRIORITY" "$TMP_PROFILE"

{
  cat "$TMP_BASE"
  echo
  cat "$TMP_PROFILE"
} > "$CONF_FILE"

chmod 600 "$CONF_FILE"

if command -v wpa_cli >/dev/null 2>&1; then
  wpa_cli -i "$INTERFACE" reconfigure >/dev/null 2>&1 || true
fi
systemctl restart wpa_supplicant >/dev/null 2>&1 || true

echo "Saved Wi-Fi profile for SSID '$SSID' in $CONF_FILE"
echo "Known networks now:"
if command -v wpa_cli >/dev/null 2>&1; then
  wpa_cli -i "$INTERFACE" list_networks || true
fi
