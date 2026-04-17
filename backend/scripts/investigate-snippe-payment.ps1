param(
    [Parameter(Mandatory = $true)]
    [string]$ProviderRequestId,
    [string]$ApiBaseUrl = "http://127.0.0.1:8000/api/v1",
    [string]$PiHost = "hph-pi01.local",
    [string]$PiUser = "hasnet_pi",
    [int]$ReconcileLimit = 100,
    [int]$SecondReconcileDelaySeconds = 10,
    [switch]$SkipSecondReconcile,
    [string]$SaveEvidencePath = ""
)

$ErrorActionPreference = "Stop"

$launcherPath = Join-Path $PSScriptRoot "investigate-snippe-payment-via-ssh.ps1"
if (-not (Test-Path -LiteralPath $launcherPath)) {
    throw "Launcher script not found: $launcherPath"
}

Write-Host "Legacy wrapper: forwarding to investigate-snippe-payment-via-ssh.ps1" -ForegroundColor Yellow

$forwardParams = @{
    ProviderRequestId = $ProviderRequestId
    PiHost = $PiHost
    PiUser = $PiUser
    RemoteApiBaseUrl = $ApiBaseUrl
    ReconcileLimit = $ReconcileLimit
    SecondReconcileDelaySeconds = $SecondReconcileDelaySeconds
}

if ($SkipSecondReconcile) {
    $forwardParams.SkipSecondReconcile = $true
}

if (-not [string]::IsNullOrWhiteSpace($SaveEvidencePath)) {
    Write-Host "Note: SaveEvidencePath is interpreted on Pi filesystem in SSH mode." -ForegroundColor DarkYellow
    $forwardParams.SaveEvidencePath = $SaveEvidencePath
}

& $launcherPath @forwardParams
