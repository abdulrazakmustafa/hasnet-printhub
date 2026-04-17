param(
    [Parameter(Mandatory = $true)]
    [string]$ProviderRequestId,
    [string]$PiHost = "hph-pi01.local",
    [string]$PiUser = "hasnet_pi",
    [Alias("ApiBaseUrl")]
    [string]$RemoteApiBaseUrl = "http://127.0.0.1:8000/api/v1",
    [int]$ReconcileLimit = 100,
    [int]$SecondReconcileDelaySeconds = 10,
    [switch]$SkipSecondReconcile,
    [string]$RemoteEnvFile = "/home/hasnet_pi/hasnet-printhub/backend/.env",
    [string]$SaveEvidencePath = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProviderRequestId.Trim().StartsWith("SN")) {
    throw "ProviderRequestId must start with 'SN'. Got: $ProviderRequestId"
}

if ($ReconcileLimit -lt 1 -or $ReconcileLimit -gt 100) {
    throw "ReconcileLimit must be between 1 and 100."
}

if ($SecondReconcileDelaySeconds -lt 0) {
    throw "SecondReconcileDelaySeconds must be >= 0."
}

$SshExe = "C:\Windows\System32\OpenSSH\ssh.exe"
$piScriptPath = Join-Path $PSScriptRoot "investigate-snippe-payment-on-pi.sh"
if (-not (Test-Path -LiteralPath $piScriptPath)) {
    throw "Pi investigation script not found: $piScriptPath"
}

function Convert-ToBashSingleQuotedLiteral([string]$Value) {
    if ($null -eq $Value) {
        return "''"
    }
    return "'" + ($Value -replace "'", "'""'""'") + "'"
}

$remoteArgs = @(
    "--provider-request-id", $ProviderRequestId,
    "--api-base-url", $RemoteApiBaseUrl,
    "--reconcile-limit", "$ReconcileLimit",
    "--second-reconcile-delay-seconds", "$SecondReconcileDelaySeconds",
    "--env-file", $RemoteEnvFile
)

if ($SkipSecondReconcile) {
    $remoteArgs += "--skip-second-reconcile"
}

if (-not [string]::IsNullOrWhiteSpace($SaveEvidencePath)) {
    $remoteArgs += @("--save-evidence-path", $SaveEvidencePath)
}

$quotedArgs = $remoteArgs | ForEach-Object { Convert-ToBashSingleQuotedLiteral $_ }
$remoteCommand = "bash -s -- " + ($quotedArgs -join " ")

Write-Host "Running Pi-native investigation script over SSH ..." -ForegroundColor Cyan
Write-Host ("Target: {0}@{1}" -f $PiUser, $PiHost) -ForegroundColor DarkCyan

$scriptContent = Get-Content -Path $piScriptPath -Raw
$scriptContent | & $SshExe -tt "$PiUser@$PiHost" $remoteCommand

if ($LASTEXITCODE -ne 0) {
    throw "Remote investigation failed with exit code $LASTEXITCODE."
}
