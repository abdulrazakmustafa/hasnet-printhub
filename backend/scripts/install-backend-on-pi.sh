#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="/home/pi/hasnet-printhub/backend"
BACKEND_USER="pi"
POSTGRES_DB="hasnet_printhub"
POSTGRES_USER="hph"
POSTGRES_PASSWORD="hph_change_me"
BIND_HOST="0.0.0.0"
PORT="8000"
INSTALL_SYSTEMD="1"

usage() {
  cat <<'USAGE'
Install Hasnet PrintHub backend directly on Raspberry Pi.

Usage:
  sudo ./install-backend-on-pi.sh [options]

Options:
  --backend-dir <path>         Backend directory (default: /home/pi/hasnet-printhub/backend)
  --backend-user <username>    Linux user that owns/runs backend (default: pi)
  --postgres-db <name>         Postgres DB name (default: hasnet_printhub)
  --postgres-user <name>       Postgres app user (default: hph)
  --postgres-password <pass>   Postgres app user password
  --bind-host <host>           Uvicorn bind host (default: 0.0.0.0)
  --port <port>                Uvicorn bind port (default: 8000)
  --install-systemd <0|1>      Install and start API systemd service (default: 1)
  -h, --help                   Show this message
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-dir)
      BACKEND_DIR="$2"
      shift 2
      ;;
    --backend-user)
      BACKEND_USER="$2"
      shift 2
      ;;
    --postgres-db)
      POSTGRES_DB="$2"
      shift 2
      ;;
    --postgres-user)
      POSTGRES_USER="$2"
      shift 2
      ;;
    --postgres-password)
      POSTGRES_PASSWORD="$2"
      shift 2
      ;;
    --bind-host)
      BIND_HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --install-systemd)
      INSTALL_SYSTEMD="$2"
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

if ! id "$BACKEND_USER" >/dev/null 2>&1; then
  echo "User '$BACKEND_USER' does not exist on this Pi." >&2
  exit 1
fi

if [[ ! -d "$BACKEND_DIR" ]]; then
  echo "Backend directory not found: $BACKEND_DIR" >&2
  exit 1
fi

if [[ ! -f "$BACKEND_DIR/requirements.txt" ]]; then
  echo "Missing requirements.txt in $BACKEND_DIR" >&2
  exit 1
fi

if [[ ! -f "$BACKEND_DIR/alembic.ini" ]]; then
  echo "Missing alembic.ini in $BACKEND_DIR" >&2
  exit 1
fi

echo "[1/6] Installing OS dependencies..."
DEBIAN_FRONTEND=noninteractive apt update
DEBIAN_FRONTEND=noninteractive apt install -y \
  python3-venv python3-pip postgresql postgresql-contrib libpq-dev

echo "[2/6] Ensuring PostgreSQL is running..."
systemctl enable postgresql >/dev/null 2>&1 || true
systemctl restart postgresql

echo "[3/6] Preparing PostgreSQL role/database..."
if [[ -z "$POSTGRES_PASSWORD" ]]; then
  echo "POSTGRES_PASSWORD cannot be empty." >&2
  exit 1
fi

if ! [[ "$POSTGRES_USER" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "POSTGRES_USER must use letters, numbers, and underscore only." >&2
  exit 1
fi

if ! [[ "$POSTGRES_DB" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "POSTGRES_DB must use letters, numbers, and underscore only." >&2
  exit 1
fi

POSTGRES_PASSWORD_ESCAPED=${POSTGRES_PASSWORD//\'/\'\'}

SQL=$(cat <<EOF
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${POSTGRES_USER}') THEN
    CREATE ROLE ${POSTGRES_USER} LOGIN PASSWORD '${POSTGRES_PASSWORD_ESCAPED}';
  ELSE
    ALTER ROLE ${POSTGRES_USER} WITH LOGIN PASSWORD '${POSTGRES_PASSWORD_ESCAPED}';
  END IF;
END
\$\$;
EOF
)
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c "$SQL"

DB_EXISTS=$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'")
if [[ "$DB_EXISTS" != "1" ]]; then
  runuser -u postgres -- createdb -O "$POSTGRES_USER" "$POSTGRES_DB"
fi
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c "GRANT ALL PRIVILEGES ON DATABASE ${POSTGRES_DB} TO ${POSTGRES_USER};"

echo "[4/6] Building Python virtual environment..."
runuser -u "$BACKEND_USER" -- python3 -m venv "$BACKEND_DIR/.venv"
runuser -u "$BACKEND_USER" -- "$BACKEND_DIR/.venv/bin/pip" install --upgrade pip
runuser -u "$BACKEND_USER" -- "$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

ENV_FILE="$BACKEND_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$BACKEND_DIR/.env.example" ]]; then
    cp "$BACKEND_DIR/.env.example" "$ENV_FILE"
  else
    touch "$ENV_FILE"
  fi
fi

set_env_key() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

SECRET_VALUE=$(grep -E '^SECRET_KEY=' "$ENV_FILE" | head -n1 | cut -d'=' -f2-)
if [[ -z "$SECRET_VALUE" || "$SECRET_VALUE" == "change_this_to_a_long_random_secret" ]]; then
  SECRET_VALUE=$(runuser -u "$BACKEND_USER" -- "$BACKEND_DIR/.venv/bin/python" - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)
fi

DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}"
set_env_key "ENV" "production"
set_env_key "DEBUG" "false"
set_env_key "SECRET_KEY" "$SECRET_VALUE"
set_env_key "DATABASE_URL" "$DATABASE_URL"
set_env_key "PAYMENT_RECONCILE_ENABLED" "true"
set_env_key "PAYMENT_RECONCILE_INTERVAL_SECONDS" "30"
set_env_key "PAYMENT_RECONCILE_BATCH_LIMIT" "25"
set_env_key "PAYMENT_RECONCILE_STARTUP_DELAY_SECONDS" "5"

chown "$BACKEND_USER:$BACKEND_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "[5/6] Applying database migrations..."
runuser -u "$BACKEND_USER" -- bash -lc "cd '$BACKEND_DIR' && '$BACKEND_DIR/.venv/bin/alembic' upgrade head"

if [[ "$INSTALL_SYSTEMD" == "1" ]]; then
  echo "[6/6] Installing backend API systemd service..."
  cat > /etc/systemd/system/hasnet-printhub-api.service <<EOF
[Unit]
Description=Hasnet PrintHub Backend API
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=$BACKEND_DIR/.env
ExecStart=$BACKEND_DIR/.venv/bin/uvicorn app.main:app --host $BIND_HOST --port $PORT
Restart=always
RestartSec=5
User=$BACKEND_USER
Group=$BACKEND_USER

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable hasnet-printhub-api
  systemctl restart hasnet-printhub-api
  systemctl --no-pager --full status hasnet-printhub-api | sed -n '1,20p'
else
  echo "[6/6] Skipping systemd installation."
fi

echo "Backend install complete."
echo "Health check: curl -sS http://127.0.0.1:$PORT/healthz"
