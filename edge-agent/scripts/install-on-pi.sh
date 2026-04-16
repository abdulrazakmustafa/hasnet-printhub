#!/usr/bin/env bash
set -euo pipefail

AGENT_DIR="/home/pi/edge-agent"
AGENT_USER="pi"
INSTALL_SYSTEMD="1"
INSTALL_AVAHI="1"
LOCKDOWN_PRINT_PATH="0"
ENABLE_UFW_LOCKDOWN="0"
ALLOW_SSH_CIDR=""

usage() {
  cat <<'USAGE'
Usage:
  sudo ./install-on-pi.sh [options]

Options:
  --agent-dir <path>         Agent directory (default: /home/pi/edge-agent)
  --agent-user <username>    Linux user that owns/runs the agent (default: pi)
  --install-systemd <0|1>    Install and start systemd service (default: 1)
  --install-avahi <0|1>      Install avahi-daemon for *.local discovery (default: 1)
  --lockdown-print-path <0|1>
                              Run CUPS lock-down script after install (default: 0)
  --enable-ufw-lockdown <0|1>
                              Enable UFW + block IPP from LAN (default: 0)
  --allow-ssh-cidr <cidr>    Optional CIDR allowed to SSH when UFW is enabled
  -h, --help                 Show this help text
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent-dir)
      AGENT_DIR="$2"
      shift 2
      ;;
    --agent-user)
      AGENT_USER="$2"
      shift 2
      ;;
    --install-systemd)
      INSTALL_SYSTEMD="$2"
      shift 2
      ;;
    --install-avahi)
      INSTALL_AVAHI="$2"
      shift 2
      ;;
    --lockdown-print-path)
      LOCKDOWN_PRINT_PATH="$2"
      shift 2
      ;;
    --enable-ufw-lockdown)
      ENABLE_UFW_LOCKDOWN="$2"
      shift 2
      ;;
    --allow-ssh-cidr)
      ALLOW_SSH_CIDR="$2"
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

if ! id "$AGENT_USER" >/dev/null 2>&1; then
  echo "User '$AGENT_USER' does not exist on this Pi." >&2
  exit 1
fi

if [[ ! -d "$AGENT_DIR" ]]; then
  echo "Agent directory not found: $AGENT_DIR" >&2
  exit 1
fi

if [[ ! -f "$AGENT_DIR/requirements.txt" ]]; then
  echo "Missing requirements.txt in $AGENT_DIR" >&2
  exit 1
fi

echo "[1/4] Installing OS dependencies..."
DEBIAN_FRONTEND=noninteractive apt update
PACKAGES=(python3-venv python3-pip openssh-server)
if [[ "$INSTALL_AVAHI" == "1" ]]; then
  PACKAGES+=(avahi-daemon)
fi
DEBIAN_FRONTEND=noninteractive apt install -y "${PACKAGES[@]}"

echo "[2/4] Building Python virtual environment..."
runuser -u "$AGENT_USER" -- python3 -m venv "$AGENT_DIR/.venv"

echo "[3/4] Installing Python dependencies..."
runuser -u "$AGENT_USER" -- "$AGENT_DIR/.venv/bin/pip" install --upgrade pip
runuser -u "$AGENT_USER" -- "$AGENT_DIR/.venv/bin/pip" install -r "$AGENT_DIR/requirements.txt"

if [[ "$INSTALL_SYSTEMD" == "1" ]]; then
  echo "[4/4] Installing systemd service..."
  cat > /etc/systemd/system/hasnet-printhub-agent.service <<EOF
[Unit]
Description=Hasnet PrintHub Edge Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$AGENT_DIR
EnvironmentFile=$AGENT_DIR/.env
ExecStart=$AGENT_DIR/.venv/bin/python $AGENT_DIR/agent.py
Restart=always
RestartSec=5
User=$AGENT_USER
Group=$AGENT_USER

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable hasnet-printhub-agent
  systemctl restart hasnet-printhub-agent
  systemctl --no-pager --full status hasnet-printhub-agent | sed -n '1,20p'
else
  echo "[4/4] Skipping systemd installation."
fi

if [[ "$LOCKDOWN_PRINT_PATH" == "1" ]]; then
  echo "[extra] Applying print-path lock-down..."
  LOCKDOWN_SCRIPT="$AGENT_DIR/scripts/lockdown-print-path.sh"
  if [[ ! -x "$LOCKDOWN_SCRIPT" ]]; then
    chmod +x "$LOCKDOWN_SCRIPT" || true
  fi
  if [[ ! -f "$LOCKDOWN_SCRIPT" ]]; then
    echo "Lock-down script not found: $LOCKDOWN_SCRIPT" >&2
    exit 1
  fi

  lockdown_args=(--enable-ufw "$ENABLE_UFW_LOCKDOWN")
  if [[ -n "$ALLOW_SSH_CIDR" ]]; then
    lockdown_args+=(--allow-ssh-cidr "$ALLOW_SSH_CIDR")
  fi

  "$LOCKDOWN_SCRIPT" "${lockdown_args[@]}"
fi

echo "Edge-agent install complete."
