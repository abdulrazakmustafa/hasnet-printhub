param(
    [Parameter(Mandatory = $true)]
    [string]$PiHost,
    [string]$PiUser = "hasnet_pi",
    [string]$RemoteBackendDir = "",
    [string]$VerifyJobId = "",
    [int]$ApiPort = 8000,
    [int]$HealthRetryCount = 12,
    [int]$HealthRetryDelaySeconds = 2
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RemoteBackendDir)) {
    $RemoteBackendDir = "/home/$PiUser/hasnet-printhub/backend"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = (Resolve-Path (Join-Path $scriptDir "..")).Path
$target = "$PiUser@$PiHost"

foreach ($tool in @("ssh", "scp")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Required command '$tool' not found in PATH."
    }
}

$filesToUpload = @(
    @{ Local = (Join-Path $backendDir "app\api\routes\admin.py"); Remote = "$RemoteBackendDir/app/api/routes/admin.py" },
    @{ Local = (Join-Path $backendDir "app\api\routes\alerts.py"); Remote = "$RemoteBackendDir/app/api/routes/alerts.py" },
    @{ Local = (Join-Path $backendDir "app\api\routes\print_jobs.py"); Remote = "$RemoteBackendDir/app/api/routes/print_jobs.py" },
    @{ Local = (Join-Path $backendDir "app\schemas\print_job.py"); Remote = "$RemoteBackendDir/app/schemas/print_job.py" }
)

foreach ($entry in $filesToUpload) {
    if (-not (Test-Path -LiteralPath $entry.Local)) {
        throw "Required file missing: $($entry.Local)"
    }

    Write-Host ("Uploading {0} to {1} ..." -f (Split-Path -Leaf $entry.Local), $target) -ForegroundColor Cyan
    & scp $entry.Local ("{0}:{1}" -f $target, $entry.Remote)
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload $($entry.Local)"
    }
}

Write-Host "Restarting backend service on Pi (sudo may prompt for password) ..." -ForegroundColor Cyan
& ssh -tt $target "sudo systemctl restart hasnet-printhub-api; sudo systemctl is-active hasnet-printhub-api"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to restart hasnet-printhub-api."
}

$healthOk = $false
for ($attempt = 1; $attempt -le $HealthRetryCount; $attempt++) {
    Write-Host ("Checking backend health (attempt {0}/{1}) ..." -f $attempt, $HealthRetryCount) -ForegroundColor DarkCyan
    & ssh -tt $target "curl -sS http://127.0.0.1:$ApiPort/api/v1/health"
    if ($LASTEXITCODE -eq 0) {
        $healthOk = $true
        break
    }

    Start-Sleep -Seconds $HealthRetryDelaySeconds
}

if (-not $healthOk) {
    throw "Failed to validate hasnet-printhub-api health after restart."
}

Write-Host "Verifying new admin/customer endpoints on Pi ..." -ForegroundColor Yellow
$verifyCommand = @(
    "curl -sS 'http://127.0.0.1:$ApiPort/api/v1/admin/devices?include_inactive=false'",
    "curl -sS 'http://127.0.0.1:$ApiPort/api/v1/alerts?limit=1'",
    "curl -sS 'http://127.0.0.1:$ApiPort/api/v1/admin/payments?limit=1'",
    "curl -sS 'http://127.0.0.1:$ApiPort/api/v1/admin/reports/today'"
) -join "; "

& ssh -tt $target $verifyCommand
if ($LASTEXITCODE -ne 0) {
    throw "Failed to verify one or more admin/customer endpoints."
}

if (-not [string]::IsNullOrWhiteSpace($VerifyJobId)) {
    $encodedJobId = [System.Uri]::EscapeDataString($VerifyJobId.Trim())
    $verifyUrl = "http://127.0.0.1:$ApiPort/api/v1/print-jobs/$encodedJobId/customer-status"
    Write-Host ("Verifying customer status endpoint with job {0} ..." -f $VerifyJobId) -ForegroundColor Cyan
    & ssh -tt $target "curl -sS '$verifyUrl'"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to verify /print-jobs/{job_id}/customer-status endpoint."
    }
}

Write-Host "Admin/customer API hotfix deploy complete." -ForegroundColor Green
