[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProfilePath,
    [switch]$SkipBackend,
    [switch]$SkipAgent,
    [switch]$ValidateOnly,
    [switch]$AllowInsecurePlaceholders
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-NotBlank {
    param(
        [AllowNull()]
        [string]$Value,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name must not be empty in kiosk profile."
    }
}

function Assert-NonPlaceholderSecret {
    param(
        [AllowNull()]
        [string]$Value,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )
    Assert-NotBlank -Value $Value -Name $Name

    if ($AllowInsecurePlaceholders) {
        return
    }

    $normalized = $Value.Trim().ToUpperInvariant()
    foreach ($token in @("CHANGE_ME", "REPLACE_ME", "YOUR_")) {
        if ($normalized.Contains($token)) {
            throw "$Name still uses a placeholder value. Update the profile before provisioning."
        }
    }
}

function Get-BoolOrDefault {
    param(
        [AllowNull()]$Value,
        [bool]$Default
    )
    if ($null -eq $Value) {
        return $Default
    }
    return [bool]$Value
}

function Get-IntOrDefault {
    param(
        [AllowNull()]$Value,
        [int]$Default
    )
    if ($null -eq $Value) {
        return $Default
    }
    return [int]$Value
}

function Invoke-StepScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StepName,
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [Parameter(Mandatory = $true)]
        [hashtable]$Arguments
    )

    Write-Host ""
    Write-Host ("========== {0} ==========" -f $StepName) -ForegroundColor Yellow
    Write-Host ("Script: {0}" -f $ScriptPath) -ForegroundColor Cyan

    & $ScriptPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$StepName failed with exit code $LASTEXITCODE."
    }
}

$resolvedProfilePath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $ProfilePath).Path)
$profileRaw = Get-Content -Path $resolvedProfilePath -Raw -Encoding UTF8
$profile = $profileRaw | ConvertFrom-Json

if ($null -eq $profile) {
    throw "Profile JSON could not be parsed: $resolvedProfilePath"
}

if ($null -eq $profile.pi) {
    throw "Profile must include 'pi' section."
}

$piHost = [string]$profile.pi.host
Assert-NotBlank -Value $piHost -Name "pi.host"

$piUser = [string]$profile.pi.user
if ([string]::IsNullOrWhiteSpace($piUser)) {
    $piUser = "hasnet_pi"
}

$kioskId = [string]$profile.kiosk_id
if ([string]::IsNullOrWhiteSpace($kioskId)) {
    $kioskId = "unnamed-kiosk"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendBootstrapPath = Join-Path $repoRoot "backend\scripts\bootstrap-backend-from-windows.ps1"
$agentBootstrapPath = Join-Path $repoRoot "edge-agent\scripts\bootstrap-from-windows.ps1"

foreach ($requiredScript in @($backendBootstrapPath, $agentBootstrapPath)) {
    if (-not (Test-Path -LiteralPath $requiredScript)) {
        throw "Required provisioning script not found: $requiredScript"
    }
}

$backendCfg = $profile.backend
$backendEnabled = if ($null -eq $backendCfg) { $true } else { Get-BoolOrDefault -Value $backendCfg.enabled -Default $true }
$backendWillRun = $backendEnabled -and (-not $SkipBackend)
$backendParams = @{}

if ($backendWillRun) {
    $remoteProjectDir = [string]$backendCfg.remote_project_dir
    if ([string]::IsNullOrWhiteSpace($remoteProjectDir)) {
        $remoteProjectDir = "/home/$piUser/hasnet-printhub"
    }

    $postgresDb = [string]$backendCfg.postgres_db
    if ([string]::IsNullOrWhiteSpace($postgresDb)) {
        $postgresDb = "hasnet_printhub"
    }

    $postgresUser = [string]$backendCfg.postgres_user
    if ([string]::IsNullOrWhiteSpace($postgresUser)) {
        $postgresUser = "hph"
    }

    $postgresPassword = [string]$backendCfg.postgres_password
    Assert-NonPlaceholderSecret -Value $postgresPassword -Name "backend.postgres_password"

    $bindHost = [string]$backendCfg.bind_host
    if ([string]::IsNullOrWhiteSpace($bindHost)) {
        $bindHost = "0.0.0.0"
    }

    $port = Get-IntOrDefault -Value $backendCfg.port -Default 8000
    if ($port -lt 1 -or $port -gt 65535) {
        throw "backend.port must be between 1 and 65535."
    }

    $backendParams = @{
        PiHost = $piHost
        PiUser = $piUser
        RemoteProjectDir = $remoteProjectDir
        PostgresDb = $postgresDb
        PostgresUser = $postgresUser
        PostgresPassword = $postgresPassword
        BindHost = $bindHost
        Port = $port
    }

    if (Get-BoolOrDefault -Value $backendCfg.no_systemd -Default $false) {
        $backendParams["NoSystemd"] = $true
    }
}

$agentCfg = $profile.agent
$agentEnabled = if ($null -eq $agentCfg) { $true } else { Get-BoolOrDefault -Value $agentCfg.enabled -Default $true }
$agentWillRun = $agentEnabled -and (-not $SkipAgent)
$agentParams = @{}

if ($agentWillRun) {
    $backendBaseUrl = [string]$agentCfg.backend_base_url
    if ([string]::IsNullOrWhiteSpace($backendBaseUrl)) {
        $backendPort = if ($backendWillRun) { [int]$backendParams.Port } else { 8000 }
        $backendBaseUrl = "http://${piHost}:$backendPort/api/v1"
    }

    $deviceCode = [string]$agentCfg.device_code
    Assert-NotBlank -Value $deviceCode -Name "agent.device_code"

    $deviceApiToken = [string]$agentCfg.device_api_token
    Assert-NonPlaceholderSecret -Value $deviceApiToken -Name "agent.device_api_token"

    $siteName = [string]$agentCfg.site_name
    if ([string]::IsNullOrWhiteSpace($siteName)) {
        $siteName = $kioskId
    }

    $agentUser = [string]$agentCfg.agent_user
    if ([string]::IsNullOrWhiteSpace($agentUser)) {
        $agentUser = $piUser
    }

    $agentParams = @{
        PiHost = $piHost
        PiUser = $agentUser
        BackendBaseUrl = $backendBaseUrl
        DeviceCode = $deviceCode
        DeviceApiToken = $deviceApiToken
        SiteName = $siteName
        MockPrint = (Get-BoolOrDefault -Value $agentCfg.mock_print -Default $false)
        HeartbeatIntervalSec = (Get-IntOrDefault -Value $agentCfg.heartbeat_interval_sec -Default 30)
        PollIntervalSec = (Get-IntOrDefault -Value $agentCfg.poll_interval_sec -Default 6)
        RequestTimeoutSec = (Get-IntOrDefault -Value $agentCfg.request_timeout_sec -Default 10)
        AgentVersion = ([string]$agentCfg.agent_version)
        FirmwareVersion = ([string]$agentCfg.firmware_version)
        PrinterName = ([string]$agentCfg.printer_name)
        StorageBaseUrl = ([string]$agentCfg.storage_base_url)
    }

    if ([string]::IsNullOrWhiteSpace($agentParams.AgentVersion)) {
        $agentParams.AgentVersion = "0.1.0"
    }
    if ([string]::IsNullOrWhiteSpace($agentParams.FirmwareVersion)) {
        $agentParams.FirmwareVersion = "raspi-os-bookworm"
    }

    if (Get-BoolOrDefault -Value $agentCfg.lockdown_print_path -Default $false) {
        $agentParams["LockdownPrintPath"] = $true
    }
    if (Get-BoolOrDefault -Value $agentCfg.enable_ufw_lockdown -Default $false) {
        $agentParams["EnableUfwLockdown"] = $true
    }

    $allowSshCidr = [string]$agentCfg.allow_ssh_cidr
    if (-not [string]::IsNullOrWhiteSpace($allowSshCidr)) {
        $agentParams["AllowSshCidr"] = $allowSshCidr
    }

    if (Get-BoolOrDefault -Value $agentCfg.skip_backend_health_check -Default $false) {
        $agentParams["SkipBackendHealthCheck"] = $true
    }
    if (Get-BoolOrDefault -Value $agentCfg.no_systemd -Default $false) {
        $agentParams["NoSystemd"] = $true
    }
    if (Get-BoolOrDefault -Value $agentCfg.no_avahi -Default $false) {
        $agentParams["NoAvahi"] = $true
    }
}

$summary = [ordered]@{
    kiosk_id = $kioskId
    profile_path = $resolvedProfilePath
    target = "$piUser@$piHost"
    validate_only = [bool]$ValidateOnly
    backend = [ordered]@{
        enabled = [bool]$backendEnabled
        skipped = [bool]$SkipBackend
        will_run = [bool]$backendWillRun
    }
    agent = [ordered]@{
        enabled = [bool]$agentEnabled
        skipped = [bool]$SkipAgent
        will_run = [bool]$agentWillRun
    }
}

Write-Host ""
Write-Host "========== KIOSK PROFILE SUMMARY ==========" -ForegroundColor Yellow
Write-Host ($summary | ConvertTo-Json -Depth 8)

if ($ValidateOnly) {
    Write-Host ""
    Write-Host "Validation-only mode completed. No remote changes were executed." -ForegroundColor Green
    exit 0
}

if ($backendWillRun) {
    Invoke-StepScript -StepName "Backend Bootstrap" -ScriptPath $backendBootstrapPath -Arguments $backendParams
}
else {
    Write-Host "Skipping backend bootstrap." -ForegroundColor DarkYellow
}

if ($agentWillRun) {
    Invoke-StepScript -StepName "Edge-Agent Bootstrap" -ScriptPath $agentBootstrapPath -Arguments $agentParams
}
else {
    Write-Host "Skipping edge-agent bootstrap." -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host ("Kiosk provisioning completed for {0} ({1})." -f $kioskId, "$piUser@$piHost") -ForegroundColor Green
