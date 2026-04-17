param(
    [Parameter(Mandatory = $true)]
    [string]$ProviderRequestId,
    [string]$PiHost = "hph-pi01.local",
    [string]$PiUser = "hasnet_pi",
    [string]$ApiBaseUrl = "http://hph-pi01.local:8000/api/v1",
    [Alias("RemoteApiBaseUrl")]
    [string]$PiApiBaseUrl = "http://127.0.0.1:8000/api/v1",
    [int]$ApiPort = 8000,
    [int]$ReconcileLimit = 100,
    [int]$SecondReconcileDelaySeconds = 10,
    [switch]$SkipSecondReconcile,
    [string]$RemoteEnvFile = "/home/hasnet_pi/hasnet-printhub/backend/.env",
    [string]$SaveRemoteEvidencePath = "",
    [string]$SaveLocalSummaryPath = ""
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

if (-not $ProviderRequestId.Trim().StartsWith("SN")) {
    throw "ProviderRequestId must start with 'SN'. Got: $ProviderRequestId"
}

if ($ReconcileLimit -lt 1 -or $ReconcileLimit -gt 100) {
    throw "ReconcileLimit must be between 1 and 100."
}

if ($SecondReconcileDelaySeconds -lt 0) {
    throw "SecondReconcileDelaySeconds must be >= 0."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$investigateScript = Join-Path $scriptDir "investigate-snippe-payment-via-ssh.ps1"
if (-not (Test-Path -LiteralPath $investigateScript)) {
    throw "Required script not found: $investigateScript"
}

$SshExe = "C:\Windows\System32\OpenSSH\ssh.exe"
if (-not (Test-Path -LiteralPath $SshExe)) {
    $SshExe = "ssh"
}

$ApiBaseUrl = $ApiBaseUrl.TrimEnd("/")
$target = "$PiUser@$PiHost"

Write-Host ""
Write-Host "================ DAILY OPERATOR PACK ================" -ForegroundColor Yellow
Write-Host ("Provider Request ID: {0}" -f $ProviderRequestId) -ForegroundColor Cyan
Write-Host ("Target Pi: {0}" -f $target) -ForegroundColor Cyan

Write-Host ""
Write-Host "Step 1/4: Pi service + backend health check ..." -ForegroundColor Yellow
$healthCommand = "sudo systemctl is-active hasnet-printhub-api; sudo systemctl is-active hasnet-printhub-agent; curl -sS http://127.0.0.1:$ApiPort/api/v1/health"
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$healthOutput = & $SshExe -tt $target $healthCommand 2>&1
$healthExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($healthExitCode -ne 0) {
    throw "Health check failed over SSH (exit $healthExitCode)."
}

$healthLines = @($healthOutput | ForEach-Object { "$_" })
$serviceStates = @()
$healthJsonLine = ""

foreach ($line in $healthLines) {
    $trimmed = $line.Trim()
    if ($trimmed -match "^(active|inactive|failed|activating|deactivating|unknown)$") {
        $serviceStates += $trimmed
        continue
    }

    if ([string]::IsNullOrWhiteSpace($healthJsonLine) -and $trimmed.StartsWith("{") -and $trimmed.Contains('"status"')) {
        $healthJsonLine = $trimmed
    }
}

$apiServiceState = if ($serviceStates.Count -ge 1) { $serviceStates[0] } else { "unknown" }
$agentServiceState = if ($serviceStates.Count -ge 2) { $serviceStates[1] } else { "unknown" }
$apiHealthStatus = "unknown"

if (-not [string]::IsNullOrWhiteSpace($healthJsonLine)) {
    try {
        $healthJson = $healthJsonLine | ConvertFrom-Json
        if ($healthJson.status) {
            $apiHealthStatus = "$($healthJson.status)".Trim().ToLower()
        }
    }
    catch {
        $apiHealthStatus = "parse_error"
    }
}

Write-Host ("- api_service: {0}" -f $apiServiceState)
Write-Host ("- agent_service: {0}" -f $agentServiceState)
Write-Host ("- api_health: {0}" -f $apiHealthStatus)

Write-Host ""
Write-Host "Step 2/4: Provider reconcile + provider status via Pi script ..." -ForegroundColor Yellow
$investigateArgs = @(
    "-ProviderRequestId", $ProviderRequestId,
    "-PiHost", $PiHost,
    "-PiUser", $PiUser,
    "-RemoteApiBaseUrl", $PiApiBaseUrl,
    "-ReconcileLimit", "$ReconcileLimit",
    "-SecondReconcileDelaySeconds", "$SecondReconcileDelaySeconds",
    "-RemoteEnvFile", $RemoteEnvFile
)

if ($SkipSecondReconcile) {
    $investigateArgs += "-SkipSecondReconcile"
}

if (-not [string]::IsNullOrWhiteSpace($SaveRemoteEvidencePath)) {
    $investigateArgs += @("-SaveEvidencePath", $SaveRemoteEvidencePath)
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $investigateScript @investigateArgs
if ($LASTEXITCODE -ne 0) {
    throw "Provider investigation step failed (exit $LASTEXITCODE)."
}

Write-Host ""
Write-Host "Step 3/4: Backend payment snapshot check ..." -ForegroundColor Yellow
$encodedRef = [System.Uri]::EscapeDataString($ProviderRequestId.Trim())
$snapshotUrl = "$ApiBaseUrl/payments/by-provider-ref/$encodedRef"
Write-Host ("Fetching: {0}" -f $snapshotUrl) -ForegroundColor DarkCyan

try {
    $snapshot = Invoke-RestMethod -Method GET -Uri $snapshotUrl
}
catch {
    $response = $_.Exception.Response
    if ($response -and [int]$response.StatusCode -eq 404) {
        Write-Host "Snapshot endpoint not found (404) on target API." -ForegroundColor Red
        Write-Host "Deploy hotfix first:" -ForegroundColor Yellow
        Write-Host ("powershell -ExecutionPolicy Bypass -File .\scripts\deploy-payment-snapshot-hotfix-to-pi.ps1 -PiHost {0} -VerifyProviderRequestId {1}" -f $PiHost, $ProviderRequestId) -ForegroundColor Yellow
    }

    throw
}

$paymentStatus = ("{0}" -f $snapshot.payment_status).Trim().ToLower()
$printJobStatus = ("{0}" -f $snapshot.print_job_status).Trim().ToLower()
$printJobPaymentStatus = ("{0}" -f $snapshot.print_job_payment_status).Trim().ToLower()
$devicePrinterStatus = ("{0}" -f $snapshot.device_printer_status).Trim().ToLower()

Write-Host ("- payment_status: {0}" -f $snapshot.payment_status)
Write-Host ("- print_job_status: {0}" -f $snapshot.print_job_status)
Write-Host ("- print_job_payment_status: {0}" -f $snapshot.print_job_payment_status)
Write-Host ("- device_code: {0}" -f $snapshot.device_code)
Write-Host ("- device_printer_status: {0}" -f $snapshot.device_printer_status)

Write-Host ""
Write-Host "Step 4/4: Final operator decision ..." -ForegroundColor Yellow
$decision = "KEEP_BLOCKED_PENDING"
$action = "No printing. Keep waiting and re-run reconcile/provider checks."

if ($paymentStatus -in @("confirmed", "completed", "paid", "successful", "success")) {
    if ($printJobPaymentStatus -in @("confirmed", "paid", "successful", "success", "completed")) {
        if ($printJobStatus -in @("printed", "completed", "done")) {
            $decision = "PAYMENT_CONFIRMED_AND_PRINT_RECORDED"
            $action = "Backend already shows printed. If printer was offline, verify physical paper once on-site."
        }
        else {
            $decision = "ALLOW_DISPATCH_AFTER_RECONCILE"
            $action = "Payment confirmed. Verify edge-agent dispatch and printer queue/device state."
        }
    }
    else {
        $decision = "RECONCILE_REQUIRED"
        $action = "Payment is confirmed but print-job payment status not confirmed yet. Reconcile and retry checks."
    }
}
elseif ($paymentStatus -in @("failed", "cancelled", "canceled", "declined", "expired", "voided")) {
    $decision = "BLOCK_AND_RETRY_NEW_PAYMENT"
    $action = "Do not print. Ask customer to retry with a new transaction."
}

Write-Host ""
Write-Host "Decision Summary" -ForegroundColor Green
Write-Host ("- provider_request_id: {0}" -f $ProviderRequestId)
Write-Host ("- decision: {0}" -f $decision)
Write-Host ("- action: {0}" -f $action)

$summary = [ordered]@{
    checked_at_local = (Get-Date).ToString("o")
    checked_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    provider_request_id = $ProviderRequestId
    pi_host = $PiHost
    health = [ordered]@{
        api_service = $apiServiceState
        agent_service = $agentServiceState
        api_health = $apiHealthStatus
    }
    snapshot = $snapshot
    decision = $decision
    action = $action
}

if (-not [string]::IsNullOrWhiteSpace($SaveLocalSummaryPath)) {
    $fullPath = [System.IO.Path]::GetFullPath($SaveLocalSummaryPath)
    $parent = Split-Path -Parent $fullPath
    if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    $summary | ConvertTo-Json -Depth 10 | Set-Content -Path $fullPath -Encoding UTF8
    Write-Host ("Summary JSON saved: {0}" -f $fullPath) -ForegroundColor Green
}

Write-Host ""
Write-Host "Daily operator pack completed." -ForegroundColor Green
