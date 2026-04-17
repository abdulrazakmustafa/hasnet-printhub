param(
    [Parameter(Mandatory = $true)]
    [string]$ProviderRequestId,
    [string]$ApiBaseUrl = "http://hph-pi01.local:8000/api/v1",
    [string]$PiHost = "hph-pi01.local",
    [string]$PiUser = "hasnet_pi",
    [int]$ReconcileLimit = 100,
    [int]$SecondReconcileDelaySeconds = 10,
    [switch]$SkipSecondReconcile,
    [string]$SaveEvidencePath = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProviderRequestId.Trim().StartsWith("SN")) {
    throw "ProviderRequestId must start with 'SN'. Got: $ProviderRequestId"
}

if ($ReconcileLimit -lt 1 -or $ReconcileLimit -gt 100) {
    throw "ReconcileLimit must be between 1 and 100."
}

$ApiBaseUrl = $ApiBaseUrl.TrimEnd("/")
$SshExe = "C:\Windows\System32\OpenSSH\ssh.exe"

function Invoke-Reconcile([string]$BaseUrl, [int]$Limit) {
    $uri = "$BaseUrl/admin/payments/reconcile?limit=$Limit"
    return Invoke-RestMethod -Method POST -Uri $uri
}

Write-Host "Step 1/3: Reconcile pending payments ..." -ForegroundColor Cyan
$reconcileOne = Invoke-Reconcile -BaseUrl $ApiBaseUrl -Limit $ReconcileLimit
Write-Host ("Reconcile #1 => status={0}, synced={1}, limit={2}" -f $reconcileOne.status, $reconcileOne.synced, $reconcileOne.limit) -ForegroundColor Green

Write-Host "Step 2/3: Query Snippe provider status on Pi ..." -ForegroundColor Cyan
$remoteScriptTemplate = @'
set -euo pipefail
ENV=/home/__PIUSER__/hasnet-printhub/backend/.env
BASE=$(sed -n 's/^SNIPPE_BASE_URL=//p' "$ENV")
KEY=$(sed -n 's/^SNIPPE_API_KEY=//p' "$ENV")
REF="__REF__"
# Defend against CRLF or stray spaces in .env values.
BASE="${BASE//$'\r'/}"
KEY="${KEY//$'\r'/}"
BASE="$(echo "$BASE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
KEY="$(echo "$KEY" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
REF="${REF//$'\r'/}"
if [ -z "$BASE" ] || [ -z "$KEY" ]; then
  echo "SNIPPE_BASE_URL or SNIPPE_API_KEY is empty in $ENV" >&2
  exit 2
fi
case "$BASE" in
  http://*|https://*) ;;
  *)
    echo "SNIPPE_BASE_URL is invalid: [$BASE]" >&2
    exit 2
    ;;
esac
curl -sS -H "Authorization: Bearer $KEY" "$BASE/v1/payments/$REF"
'@
$remoteScript = $remoteScriptTemplate.Replace("__PIUSER__", $PiUser).Replace("__REF__", $ProviderRequestId)
$providerRaw = $remoteScript | & $SshExe "$PiUser@$PiHost" "bash -s" 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "SSH/provider query failed: $providerRaw"
}

$providerJsonLine = ($providerRaw | ForEach-Object { $_.ToString() } | Where-Object { $_.Trim().StartsWith("{") } | Select-Object -Last 1)
if ([string]::IsNullOrWhiteSpace($providerJsonLine)) {
    throw "Could not parse provider JSON. Raw output: $providerRaw"
}

$provider = $providerJsonLine | ConvertFrom-Json
$providerStatus = ($provider.data.status | ForEach-Object { "$_" }).Trim().ToLower()
Write-Host ("Provider => status={0}, reference={1}" -f $providerStatus, $ProviderRequestId) -ForegroundColor Green

$reconcileTwo = $null
if (-not $SkipSecondReconcile) {
    Write-Host ("Step 3/3: Waiting {0}s then reconcile again ..." -f $SecondReconcileDelaySeconds) -ForegroundColor Cyan
    Start-Sleep -Seconds $SecondReconcileDelaySeconds
    $reconcileTwo = Invoke-Reconcile -BaseUrl $ApiBaseUrl -Limit $ReconcileLimit
    Write-Host ("Reconcile #2 => status={0}, synced={1}, limit={2}" -f $reconcileTwo.status, $reconcileTwo.synced, $reconcileTwo.limit) -ForegroundColor Green
}

$decision = "KEEP_BLOCKED_PENDING"
$action = "No printing. Keep waiting/escalate if >5min."

if ($providerStatus -in @("completed", "confirmed", "paid", "successful", "success")) {
    $decision = "ALLOW_DISPATCH_AFTER_RECONCILE"
    $action = "Payment is successful at provider. Reconcile and verify edge-agent dispatch/print."
} elseif ($providerStatus -in @("failed", "cancelled", "canceled", "declined", "expired", "voided")) {
    $decision = "BLOCK_AND_RETRY_NEW_PAYMENT"
    $action = "Do not print. Ask customer to retry with a new transaction."
}

$nowUtc = (Get-Date).ToUniversalTime().ToString("o")
$summary = [ordered]@{
    checked_at_utc = $nowUtc
    provider_request_id = $ProviderRequestId
    provider_status = $providerStatus
    decision = $decision
    action = $action
    reconcile_1 = $reconcileOne
    reconcile_2 = $reconcileTwo
    provider_payload = $provider
}

Write-Host ""
Write-Host "Decision Summary" -ForegroundColor Yellow
Write-Host ("- provider_request_id: {0}" -f $summary.provider_request_id)
Write-Host ("- provider_status: {0}" -f $summary.provider_status)
Write-Host ("- decision: {0}" -f $summary.decision)
Write-Host ("- action: {0}" -f $summary.action)

if (-not [string]::IsNullOrWhiteSpace($SaveEvidencePath)) {
    $json = $summary | ConvertTo-Json -Depth 20
    $dir = Split-Path -Parent $SaveEvidencePath
    if (-not [string]::IsNullOrWhiteSpace($dir) -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    Set-Content -Path $SaveEvidencePath -Value $json -Encoding UTF8
    Write-Host ("Evidence saved: {0}" -f $SaveEvidencePath) -ForegroundColor DarkCyan
}
