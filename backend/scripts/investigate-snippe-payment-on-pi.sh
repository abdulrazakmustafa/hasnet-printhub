#!/usr/bin/env bash
set -euo pipefail

provider_request_id=""
api_base_url="http://127.0.0.1:8000/api/v1"
reconcile_limit=100
second_reconcile_delay_seconds=10
skip_second_reconcile=0
env_file="/home/hasnet_pi/hasnet-printhub/backend/.env"
save_evidence_path=""

usage() {
  cat <<'EOF'
Usage:
  investigate-snippe-payment-on-pi.sh --provider-request-id SN... [options]

Options:
  --provider-request-id <SN...>                Required provider request id.
  --api-base-url <url>                         Backend API base url on Pi. Default: http://127.0.0.1:8000/api/v1
  --reconcile-limit <1-100>                    Reconcile batch limit. Default: 100
  --second-reconcile-delay-seconds <n>         Wait before second reconcile. Default: 10
  --skip-second-reconcile                       Skip second reconcile call.
  --env-file <path>                            Backend env path. Default: /home/hasnet_pi/hasnet-printhub/backend/.env
  --save-evidence-path <path>                  Optional path on Pi to write JSON evidence.
  -h, --help                                   Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider-request-id)
      provider_request_id="${2:-}"
      shift 2
      ;;
    --api-base-url)
      api_base_url="${2:-}"
      shift 2
      ;;
    --reconcile-limit)
      reconcile_limit="${2:-}"
      shift 2
      ;;
    --second-reconcile-delay-seconds)
      second_reconcile_delay_seconds="${2:-}"
      shift 2
      ;;
    --skip-second-reconcile)
      skip_second_reconcile=1
      shift
      ;;
    --env-file)
      env_file="${2:-}"
      shift 2
      ;;
    --save-evidence-path)
      save_evidence_path="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${provider_request_id}" ]]; then
  echo "Missing required argument: --provider-request-id" >&2
  exit 1
fi

if [[ "${provider_request_id}" != SN* ]]; then
  echo "Provider request id must start with SN. Got: ${provider_request_id}" >&2
  exit 1
fi

if ! [[ "${reconcile_limit}" =~ ^[0-9]+$ ]] || (( reconcile_limit < 1 || reconcile_limit > 100 )); then
  echo "reconcile-limit must be an integer between 1 and 100. Got: ${reconcile_limit}" >&2
  exit 1
fi

if ! [[ "${second_reconcile_delay_seconds}" =~ ^[0-9]+$ ]]; then
  echo "second-reconcile-delay-seconds must be a non-negative integer. Got: ${second_reconcile_delay_seconds}" >&2
  exit 1
fi

if [[ ! -f "${env_file}" ]]; then
  echo "Env file not found: ${env_file}" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required on Pi." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required on Pi for JSON parsing." >&2
  exit 1
fi

api_base_url="${api_base_url%/}"

read_env_value() {
  local key="$1"
  local raw
  raw="$(grep -E "^${key}=" "${env_file}" | tail -n 1 | cut -d= -f2- || true)"
  raw="${raw%%#*}"
  raw="${raw//$'\r'/}"
  raw="$(printf '%s' "${raw}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  raw="${raw%\"}"
  raw="${raw#\"}"
  raw="${raw%\'}"
  raw="${raw#\'}"
  printf '%s' "${raw}"
}

snippe_base_url="$(read_env_value SNIPPE_BASE_URL)"
snippe_api_key="$(read_env_value SNIPPE_API_KEY)"

if [[ -z "${snippe_base_url}" || -z "${snippe_api_key}" ]]; then
  echo "SNIPPE_BASE_URL or SNIPPE_API_KEY is empty in ${env_file}" >&2
  exit 2
fi

case "${snippe_base_url}" in
  http://*|https://*)
    ;;
  *)
    echo "SNIPPE_BASE_URL is invalid: [${snippe_base_url}]" >&2
    exit 2
    ;;
esac

echo "Step 1/3: Reconcile pending payments ..."
reconcile_one_json="$(curl -sS -X POST "${api_base_url}/admin/payments/reconcile?limit=${reconcile_limit}")"
IFS=$'\t' read -r reconcile_one_status reconcile_one_synced reconcile_one_limit <<< "$(printf '%s' "${reconcile_one_json}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(f"{d.get(\"status\",\"\")}\t{d.get(\"synced\",\"\")}\t{d.get(\"limit\",\"\")}")')"
echo "Reconcile #1 => status=${reconcile_one_status}, synced=${reconcile_one_synced}, limit=${reconcile_one_limit}"

echo "Step 2/3: Query Snippe provider status on Pi ..."
provider_json="$(curl -sS -H "Authorization: Bearer ${snippe_api_key}" "${snippe_base_url}/v1/payments/${provider_request_id}")"
provider_status="$(printf '%s' "${provider_json}" | python3 -c 'import json,sys; d=json.load(sys.stdin); data=d.get("data") or {}; print((data.get("status") or d.get("status") or "").strip().lower())')"
echo "Provider => status=${provider_status}, reference=${provider_request_id}"

reconcile_two_json=""
if (( skip_second_reconcile == 0 )); then
  echo "Step 3/3: Waiting ${second_reconcile_delay_seconds}s then reconcile again ..."
  sleep "${second_reconcile_delay_seconds}"
  reconcile_two_json="$(curl -sS -X POST "${api_base_url}/admin/payments/reconcile?limit=${reconcile_limit}")"
  IFS=$'\t' read -r reconcile_two_status reconcile_two_synced reconcile_two_limit <<< "$(printf '%s' "${reconcile_two_json}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(f"{d.get(\"status\",\"\")}\t{d.get(\"synced\",\"\")}\t{d.get(\"limit\",\"\")}")')"
  echo "Reconcile #2 => status=${reconcile_two_status}, synced=${reconcile_two_synced}, limit=${reconcile_two_limit}"
fi

decision="KEEP_BLOCKED_PENDING"
action="No printing. Keep waiting/escalate if >5min."

case "${provider_status}" in
  completed|confirmed|paid|successful|success)
    decision="ALLOW_DISPATCH_AFTER_RECONCILE"
    action="Payment successful at provider. Reconcile and verify edge-agent dispatch/print."
    ;;
  failed|cancelled|canceled|declined|expired|voided)
    decision="BLOCK_AND_RETRY_NEW_PAYMENT"
    action="Do not print. Ask customer to retry with a new transaction."
    ;;
esac

checked_at_utc="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

echo ""
echo "Decision Summary"
echo "- provider_request_id: ${provider_request_id}"
echo "- provider_status: ${provider_status}"
echo "- decision: ${decision}"
echo "- action: ${action}"

if [[ -n "${save_evidence_path}" ]]; then
  export R1_JSON="${reconcile_one_json}"
  export R2_JSON="${reconcile_two_json}"
  export PROVIDER_JSON="${provider_json}"
  export CHECKED_AT_UTC="${checked_at_utc}"
  export PROVIDER_REQUEST_ID="${provider_request_id}"
  export PROVIDER_STATUS="${provider_status}"
  export DECISION="${decision}"
  export ACTION="${action}"
  export SAVE_PATH="${save_evidence_path}"
  python3 - <<'PY'
import datetime
import json
import os
from pathlib import Path

reconcile_1 = json.loads(os.environ["R1_JSON"])
reconcile_2 = json.loads(os.environ["R2_JSON"]) if os.environ.get("R2_JSON") else None
provider_payload = json.loads(os.environ["PROVIDER_JSON"])

out = {
    "checked_at_utc": os.environ["CHECKED_AT_UTC"],
    "provider_request_id": os.environ["PROVIDER_REQUEST_ID"],
    "provider_status": os.environ["PROVIDER_STATUS"],
    "decision": os.environ["DECISION"],
    "action": os.environ["ACTION"],
    "reconcile_1": reconcile_1,
    "reconcile_2": reconcile_2,
    "provider_payload": provider_payload,
}

path = Path(os.environ["SAVE_PATH"])
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Evidence saved: {path}")
PY
fi
