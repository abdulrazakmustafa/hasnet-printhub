param(
    [Parameter(Mandatory = $true)]
    [string]$PiHost,
    [string]$PiUser = "hasnet_pi",
    [string]$PiPassword = "",
    [string]$RemoteBackendDir = "",
    [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = (Resolve-Path (Join-Path $scriptDir "..")).Path
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"
$deployPy = Join-Path $scriptDir "deploy_kiosk_hotfix_paramiko.py"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python venv not found: $pythonExe"
}

if (-not (Test-Path -LiteralPath $deployPy)) {
    throw "Deploy helper script not found: $deployPy"
}

if ([string]::IsNullOrWhiteSpace($PiPassword)) {
    $secure = Read-Host -Prompt "Pi SSH password for $PiUser@$PiHost" -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $PiPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$args = @(
    $deployPy,
    "--pi-host", $PiHost,
    "--pi-user", $PiUser,
    "--pi-password", $PiPassword,
    "--api-port", "$ApiPort"
)

if (-not [string]::IsNullOrWhiteSpace($RemoteBackendDir)) {
    $args += @("--remote-backend-dir", $RemoteBackendDir)
}

Write-Host ("Deploying kiosk hotfix to {0}@{1} ..." -f $PiUser, $PiHost) -ForegroundColor Cyan
& $pythonExe @args
if ($LASTEXITCODE -ne 0) {
    throw "Paramiko deploy helper failed with exit code $LASTEXITCODE."
}

Write-Host "Kiosk hotfix deployment complete." -ForegroundColor Green
