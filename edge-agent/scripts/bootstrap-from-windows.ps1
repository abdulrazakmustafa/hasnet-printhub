[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PiHost,

    [string]$PiUser = "pi",
    [string]$BackendBaseUrl = "http://192.168.0.210:8000/api/v1",
    [string]$DeviceCode = "pi-kiosk-001",
    [string]$DeviceApiToken = "",
    [string]$SiteName = "Kiosk 1",
    [bool]$MockPrint = $true,
    [int]$HeartbeatIntervalSec = 30,
    [int]$PollIntervalSec = 6,
    [int]$RequestTimeoutSec = 10,
    [string]$AgentVersion = "0.1.0",
    [string]$FirmwareVersion = "raspi-os-bookworm",
    [string]$PrinterName = "",
    [string]$StorageBaseUrl = "",
    [switch]$LockdownPrintPath,
    [switch]$EnableUfwLockdown,
    [string]$AllowSshCidr = "",
    [switch]$SkipBackendHealthCheck,
    [switch]$NoSystemd,
    [switch]$NoAvahi
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

foreach ($tool in @("ssh", "scp")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Required command '$tool' was not found in PATH."
    }
}

$backendUrl = $BackendBaseUrl.TrimEnd("/")
$healthUrl = "$backendUrl/health"
$target = "$PiUser@$PiHost"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$edgeAgentDir = (Resolve-Path (Join-Path $scriptDir "..")).Path
$remoteAgentDir = "/home/$PiUser/edge-agent"

if (-not $SkipBackendHealthCheck) {
    try {
        $healthResp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 12
        if ($healthResp.StatusCode -ne 200) {
            throw "Unexpected status code $($healthResp.StatusCode)"
        }
        Write-Host "Backend health OK at $healthUrl"
    }
    catch {
        throw "Backend health check failed at $healthUrl. $($_.Exception.Message)"
    }
}

Write-Host "Checking SSH connectivity to $target ..."
Invoke-CheckedExternal -FilePath "ssh" -Arguments @($target, "echo connected") -FailureMessage "SSH connectivity check failed"

Write-Host "Preparing remote directories ..."
Invoke-CheckedExternal -FilePath "ssh" -Arguments @($target, "mkdir -p $remoteAgentDir/systemd $remoteAgentDir/scripts $remoteAgentDir/spool") -FailureMessage "Unable to prepare remote directories"

$filesToCopy = @(
    "agent.py",
    "config.py",
    "heartbeat.py",
    "job_runner.py",
    "monitor.py",
    "requirements.txt",
    ".env.example",
    "README.md"
)

foreach ($fileName in $filesToCopy) {
    $sourcePath = Join-Path $edgeAgentDir $fileName
    $destinationPath = "${target}:$remoteAgentDir/$fileName"
    Write-Host "Copying $fileName ..."
    Invoke-CheckedExternal -FilePath "scp" -Arguments @($sourcePath, $destinationPath) -FailureMessage "Failed to copy $fileName"
}

Write-Host "Copying service template and install script ..."
Invoke-CheckedExternal -FilePath "scp" -Arguments @(
    (Join-Path $edgeAgentDir "systemd\hasnet-printhub-agent.service"),
    "${target}:$remoteAgentDir/systemd/hasnet-printhub-agent.service"
) -FailureMessage "Failed to copy systemd service template"

Invoke-CheckedExternal -FilePath "scp" -Arguments @(
    (Join-Path $edgeAgentDir "scripts\install-on-pi.sh"),
    "${target}:$remoteAgentDir/scripts/install-on-pi.sh"
) -FailureMessage "Failed to copy Pi install script"

Invoke-CheckedExternal -FilePath "scp" -Arguments @(
    (Join-Path $edgeAgentDir "scripts\add-wifi-profile.sh"),
    "${target}:$remoteAgentDir/scripts/add-wifi-profile.sh"
) -FailureMessage "Failed to copy Wi-Fi profile script"

Invoke-CheckedExternal -FilePath "scp" -Arguments @(
    (Join-Path $edgeAgentDir "scripts\lockdown-print-path.sh"),
    "${target}:$remoteAgentDir/scripts/lockdown-print-path.sh"
) -FailureMessage "Failed to copy lock-down script"

Invoke-CheckedExternal -FilePath "scp" -Arguments @(
    (Join-Path $edgeAgentDir "scripts\configure-hotspot-ap.sh"),
    "${target}:$remoteAgentDir/scripts/configure-hotspot-ap.sh"
) -FailureMessage "Failed to copy hotspot setup script"

$tempEnvPath = Join-Path $env:TEMP ("hph-edge-agent-{0}.env" -f ([Guid]::NewGuid().ToString("N")))
$envContent = @(
    "BACKEND_BASE_URL=$backendUrl"
    "DEVICE_CODE=$DeviceCode"
    "DEVICE_API_TOKEN=$DeviceApiToken"
    "SITE_NAME=$SiteName"
    "HEARTBEAT_INTERVAL_SEC=$HeartbeatIntervalSec"
    "POLL_INTERVAL_SEC=$PollIntervalSec"
    "REQUEST_TIMEOUT_SEC=$RequestTimeoutSec"
    "AGENT_VERSION=$AgentVersion"
    "FIRMWARE_VERSION=$FirmwareVersion"
    "MOCK_PRINT=$($MockPrint.ToString().ToLowerInvariant())"
    "SIMULATE_PRINT_SECONDS=4"
    "PRINTER_NAME=$PrinterName"
    "CUPS_LP_PATH=lp"
    "CUPS_LPSTAT_PATH=lpstat"
    "STORAGE_BASE_URL=$StorageBaseUrl"
) -join "`n"

# Write UTF-8 without BOM so systemd EnvironmentFile reads the first key correctly.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($tempEnvPath, $envContent, $utf8NoBom)

try {
    Write-Host "Uploading .env configuration ..."
    Invoke-CheckedExternal -FilePath "scp" -Arguments @($tempEnvPath, "${target}:$remoteAgentDir/.env") -FailureMessage "Failed to upload .env"
}
finally {
    Remove-Item -Path $tempEnvPath -Force -ErrorAction SilentlyContinue
}

$installSystemd = if ($NoSystemd) { "0" } else { "1" }
$installAvahi = if ($NoAvahi) { "0" } else { "1" }

Write-Host "Running Pi installer (this may prompt for sudo password) ..."
$installCmd = "sudo $remoteAgentDir/scripts/install-on-pi.sh --agent-dir $remoteAgentDir --agent-user $PiUser --install-systemd $installSystemd --install-avahi $installAvahi"
if ($LockdownPrintPath) {
    $installCmd += " --lockdown-print-path 1"
    $installCmd += " --enable-ufw-lockdown $([int]$EnableUfwLockdown)"
    if ($AllowSshCidr) {
        $installCmd += " --allow-ssh-cidr $AllowSshCidr"
    }
}

$remoteInstallCmd = @(
    "chmod +x $remoteAgentDir/scripts/install-on-pi.sh"
    "chmod +x $remoteAgentDir/scripts/add-wifi-profile.sh"
    "chmod +x $remoteAgentDir/scripts/lockdown-print-path.sh"
    "chmod +x $remoteAgentDir/scripts/configure-hotspot-ap.sh"
    $installCmd
) -join " && "

Invoke-CheckedExternal -FilePath "ssh" -Arguments @("-tt", $target, $remoteInstallCmd) -FailureMessage "Pi install script failed"

if ($NoSystemd) {
    Write-Host "Install finished without systemd."
    Write-Host "Run foreground test with:"
    Write-Host "ssh $target 'cd $remoteAgentDir && ./.venv/bin/python agent.py'"
}
else {
    Write-Host "Validating service status and recent logs ..."
    Invoke-CheckedExternal -FilePath "ssh" -Arguments @(
        "-tt",
        $target,
        "sudo systemctl is-active hasnet-printhub-agent && sudo journalctl -u hasnet-printhub-agent -n 25 --no-pager"
    ) -FailureMessage "Service validation failed"
}

Write-Host "Bootstrap complete for $target"
