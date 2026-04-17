param(
    [Parameter(Mandatory = $true)]
    [string]$PiHost,
    [string]$PiUser = "hasnet_pi",
    [string]$RemoteBackendDir = "",
    [string]$VerifyProviderRequestId = "",
    [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RemoteBackendDir)) {
    $RemoteBackendDir = "/home/$PiUser/hasnet-printhub/backend"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = (Resolve-Path (Join-Path $scriptDir "..")).Path

$localRouteFile = Join-Path $backendDir "app\api\routes\payments.py"
$localSchemaFile = Join-Path $backendDir "app\schemas\payment.py"

foreach ($p in @($localRouteFile, $localSchemaFile)) {
    if (-not (Test-Path -LiteralPath $p)) {
        throw "Required file missing: $p"
    }
}

foreach ($tool in @("ssh", "scp")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Required command '$tool' not found in PATH."
    }
}

$target = "$PiUser@$PiHost"
$remoteRouteFile = "$RemoteBackendDir/app/api/routes/payments.py"
$remoteSchemaFile = "$RemoteBackendDir/app/schemas/payment.py"

Write-Host ("Uploading payments route to {0} ..." -f $target) -ForegroundColor Cyan
& scp $localRouteFile "${target}:$remoteRouteFile"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload payments.py"
}

Write-Host ("Uploading payment schema to {0} ..." -f $target) -ForegroundColor Cyan
& scp $localSchemaFile "${target}:$remoteSchemaFile"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload payment schema"
}

Write-Host "Restarting backend service on Pi (sudo may prompt for password) ..." -ForegroundColor Cyan
& ssh -tt $target "sudo systemctl restart hasnet-printhub-api; sudo systemctl is-active hasnet-printhub-api; curl -sS http://127.0.0.1:$ApiPort/api/v1/health"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to restart/validate hasnet-printhub-api."
}

if (-not [string]::IsNullOrWhiteSpace($VerifyProviderRequestId)) {
    $encodedRef = [System.Uri]::EscapeDataString($VerifyProviderRequestId.Trim())
    $verifyUrl = "http://127.0.0.1:$ApiPort/api/v1/payments/by-provider-ref/$encodedRef"
    Write-Host ("Verifying new endpoint on Pi with ref {0} ..." -f $VerifyProviderRequestId) -ForegroundColor Cyan
    & ssh -tt $target "curl -sS '$verifyUrl'"
    if ($LASTEXITCODE -ne 0) {
        throw "Endpoint verification failed on Pi."
    }
}

Write-Host "Hotfix deploy complete." -ForegroundColor Green
