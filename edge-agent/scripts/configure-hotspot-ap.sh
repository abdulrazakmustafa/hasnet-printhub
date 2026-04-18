#!/usr/bin/env bash
set -euo pipefail

INTERFACE="wlan0"
SSID=""
SECURITY="WPA"
PASSPHRASE=""
COUNTRY="TZ"
CHANNEL="6"
GATEWAY_IP="10.55.0.1"
DHCP_START="10.55.0.20"
DHCP_END="10.55.0.220"

usage() {
  cat <<'USAGE'
Usage: configure-hotspot-ap.sh --ssid <name> [options]

Options:
  --interface <name>      Wireless interface (default: wlan0)
  --ssid <name>           Hotspot SSID (required)
  --security <WPA|NOPASS> Security mode (default: WPA)
  --passphrase <value>    WPA passphrase (required when security=WPA)
  --country <code>        Wi-Fi country code (default: TZ)
  --channel <number>      Wi-Fi channel (default: 6)
  --gateway-ip <ip>       Hotspot gateway IP (default: 10.55.0.1)
  --dhcp-start <ip>       DHCP range start (default: 10.55.0.20)
  --dhcp-end <ip>         DHCP range end (default: 10.55.0.220)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interface) INTERFACE="${2:-}"; shift 2 ;;
    --ssid) SSID="${2:-}"; shift 2 ;;
    --security) SECURITY="${2:-}"; shift 2 ;;
    --passphrase) PASSPHRASE="${2:-}"; shift 2 ;;
    --country) COUNTRY="${2:-}"; shift 2 ;;
    --channel) CHANNEL="${2:-}"; shift 2 ;;
    --gateway-ip) GATEWAY_IP="${2:-}"; shift 2 ;;
    --dhcp-start) DHCP_START="${2:-}"; shift 2 ;;
    --dhcp-end) DHCP_END="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (use sudo)." >&2
  exit 1
fi

if [[ -z "$SSID" ]]; then
  echo "--ssid is required." >&2
  exit 1
fi

SECURITY="$(echo "$SECURITY" | tr '[:lower:]' '[:upper:]')"
if [[ "$SECURITY" != "WPA" && "$SECURITY" != "NOPASS" ]]; then
  echo "--security must be WPA or NOPASS." >&2
  exit 1
fi

if [[ "$SECURITY" == "WPA" ]]; then
  if [[ ${#PASSPHRASE} -lt 8 || ${#PASSPHRASE} -gt 63 ]]; then
    echo "WPA passphrase must be 8-63 characters." >&2
    exit 1
  fi
fi

apt-get update -y
apt-get install -y hostapd dnsmasq

systemctl unmask hostapd || true
systemctl stop hostapd || true
systemctl stop dnsmasq || true

cat >/etc/hostapd/hostapd.conf <<EOF
country_code=${COUNTRY}
interface=${INTERFACE}
driver=nl80211
ssid=${SSID}
hw_mode=g
channel=${CHANNEL}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
EOF

if [[ "$SECURITY" == "WPA" ]]; then
  cat >>/etc/hostapd/hostapd.conf <<EOF
wpa=2
wpa_passphrase=${PASSPHRASE}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF
fi

if grep -q '^DAEMON_CONF=' /etc/default/hostapd; then
  sed -i 's|^DAEMON_CONF=.*|DAEMON_CONF=\"/etc/hostapd/hostapd.conf\"|' /etc/default/hostapd
else
  echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' >>/etc/default/hostapd
fi

cat >/etc/dnsmasq.d/hph-kiosk-hotspot.conf <<EOF
interface=${INTERFACE}
bind-dynamic
domain-needed
bogus-priv
dhcp-range=${DHCP_START},${DHCP_END},255.255.255.0,12h
address=/#/${GATEWAY_IP}
EOF

if [[ ! -f /etc/dhcpcd.conf.hph-backup ]]; then
  cp /etc/dhcpcd.conf /etc/dhcpcd.conf.hph-backup
fi

awk '
  BEGIN { skip = 0 }
  /# HPH_HOTSPOT_BEGIN/ { skip = 1; next }
  /# HPH_HOTSPOT_END/ { skip = 0; next }
  skip == 0 { print }
' /etc/dhcpcd.conf >/etc/dhcpcd.conf.tmp

cat >>/etc/dhcpcd.conf.tmp <<EOF
# HPH_HOTSPOT_BEGIN
interface ${INTERFACE}
    static ip_address=${GATEWAY_IP}/24
    nohook wpa_supplicant
# HPH_HOTSPOT_END
EOF
mv /etc/dhcpcd.conf.tmp /etc/dhcpcd.conf

rfkill unblock wifi || true

systemctl restart dhcpcd
systemctl restart dnsmasq
systemctl enable dnsmasq
systemctl restart hostapd
systemctl enable hostapd

echo "Hotspot configured successfully."
echo "SSID: ${SSID}"
echo "Gateway: ${GATEWAY_IP}"
