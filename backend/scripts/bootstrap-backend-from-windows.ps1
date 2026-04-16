[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PiHost,

    [string]$PiUser = "hasnet_pi",
    [string]$RemoteProjectDir = "",
    [string]$PostgresDb = "hasnet_printhub",
    [string]$PostgresUser = "hph",
    [string]$PostgresPassword = "hph_change_me",
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$NoSystemd
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-CheckedExternal {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
    }
}

foreach ($tool in @("ssh", "scp", "tar")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Required command '$tool' was not found in PATH."
    }
}

$target = "$PiUser@$PiHost"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = (Resolve-Path (Join-Path $scriptDir "..")).Path
if ([string]::IsNullOrWhiteSpace($RemoteProjectDir)) {
    $RemoteProjectDir = "/home/$PiUser/hasnet-printhub"
}
$remoteBackendDir = "$RemoteProjectDir/backend"

Write-Host "Checking SSH connectivity to $target ..."
Invoke-CheckedExternal -FilePath "ssh" -Arguments @($target, "echo connected") -FailureMessage "SSH connectivity check failed"

$tempRoot = Join-Path $env:TEMP ("hph-backend-deploy-{0}" -f ([Guid]::NewGuid().ToString("N")))
$tempBackend = Join-Path $tempRoot "backend"
$archivePath = Join-Path $env:TEMP ("hph-backend-{0}.tgz" -f ([Guid]::NewGuid().ToString("N")))

try {
    New-Item -Path $tempBackend -ItemType Directory -Force | Out-Null

    foreach ($entry in @("app", "alembic", "assets", "scripts", "requirements.txt", "alembic.ini", ".env.example")) {
        $source = Join-Path $backendDir $entry
        if (-not (Test-Path $source)) {
            throw "Missing required backend entry: $entry"
        }

        if ((Get-Item $source).PSIsContainer) {
            Copy-Item -Path $source -Destination $tempBackend -Recurse -Force
        }
        else {
            Copy-Item -Path $source -Destination $tempBackend -Force
        }
    }

    Write-Host "Packaging backend archive ..."
    Invoke-CheckedExternal -FilePath "tar" -Arguments @("-czf", $archivePath, "-C", $tempRoot, "backend") -FailureMessage "Failed to create archive"

    Write-Host "Preparing remote directory ..."
    Invoke-CheckedExternal -FilePath "ssh" -Arguments @($target, "mkdir -p $RemoteProjectDir") -FailureMessage "Failed to prepare remote project directory"

    Write-Host "Uploading backend archive ..."
    Invoke-CheckedExternal -FilePath "scp" -Arguments @($archivePath, "${target}:$RemoteProjectDir/backend.tgz") -FailureMessage "Failed to upload backend archive"

    Write-Host "Extracting backend on Pi ..."
    Invoke-CheckedExternal -FilePath "ssh" -Arguments @(
        $target,
        "rm -rf $remoteBackendDir && tar -xzf $RemoteProjectDir/backend.tgz -C $RemoteProjectDir && rm -f $RemoteProjectDir/backend.tgz"
    ) -FailureMessage "Failed to extract backend archive on Pi"

    $installSystemd = if ($NoSystemd) { "0" } else { "1" }
    $remoteInstallCmd = @(
        "chmod +x $remoteBackendDir/scripts/install-backend-on-pi.sh",
        "sudo $remoteBackendDir/scripts/install-backend-on-pi.sh --backend-dir $remoteBackendDir --backend-user $PiUser --postgres-db $PostgresDb --postgres-user $PostgresUser --postgres-password $PostgresPassword --bind-host $BindHost --port $Port --install-systemd $installSystemd"
    ) -join " && "

    Write-Host "Running backend installer on Pi (sudo may prompt for password) ..."
    Invoke-CheckedExternal -FilePath "ssh" -Arguments @("-tt", $target, $remoteInstallCmd) -FailureMessage "Backend install script failed"

    if (-not $NoSystemd) {
        Write-Host "Validating backend health and service status ..."
        Invoke-CheckedExternal -FilePath "ssh" -Arguments @(
            "-tt",
            $target,
            "curl -sS http://127.0.0.1:$Port/healthz && echo && sudo systemctl is-active hasnet-printhub-api && sudo journalctl -u hasnet-printhub-api -n 25 --no-pager"
        ) -FailureMessage "Backend service validation failed"
    }

    Write-Host "Pi backend bootstrap complete for $target"
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item -Path $tempRoot -Recurse -Force
    }
    if (Test-Path $archivePath) {
        Remove-Item -Path $archivePath -Force
    }
}
