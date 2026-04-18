[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProfilePath,
    [switch]$SkipBackend,
    [switch]$SkipAgent,
    [switch]$ValidateOnly,
    [switch]$AllowInsecurePlaceholders,
    [switch]$RunPostSmoke,
    [int]$SmokeLimit = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function ConvertTo-BashSingleQuoted {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )
    return "'" + $Value.Replace("'", "'""'""'") + "'"
}

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
        throw "$FailureMessage (exit code $LASTEXITCODE)."
    }
}

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

function Get-OriginFromApiBaseUrl {
    param(
        [AllowNull()]
        [string]$ApiBaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$FallbackHost,
        [Parameter(Mandatory = $true)]
        [int]$FallbackPort
    )

    $fallback = "http://${FallbackHost}:$FallbackPort"
    if ([string]::IsNullOrWhiteSpace($ApiBaseUrl)) {
        return $fallback
    }

    try {
        $uri = [System.Uri]$ApiBaseUrl
        if (-not $uri.Scheme -or -not $uri.Host) {
            return $fallback
        }

        if (($uri.Scheme -eq "http" -and $uri.Port -eq 80) -or ($uri.Scheme -eq "https" -and $uri.Port -eq 443)) {
            return "{0}://{1}" -f $uri.Scheme, $uri.Host
        }
        return "{0}://{1}:{2}" -f $uri.Scheme, $uri.Host, $uri.Port
    }
    catch {
        return $fallback
    }
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

if ($SmokeLimit -lt 1 -or $SmokeLimit -gt 50) {
    throw "SmokeLimit must be between 1 and 50."
}

$postSmokeScriptPath = Join-Path $repoRoot "backend\scripts\check-admin-customer-api-pack.ps1"

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

$hotspotCfg = $profile.hotspot
$hotspotEnabled = if ($null -eq $hotspotCfg) { $false } else { Get-BoolOrDefault -Value $hotspotCfg.enabled -Default $false }
$hotspotParams = @{}

if ($hotspotEnabled) {
    $hotspotInterface = [string]$hotspotCfg.interface
    if ([string]::IsNullOrWhiteSpace($hotspotInterface)) {
        $hotspotInterface = "wlan0"
    }

    $hotspotSsid = [string]$hotspotCfg.ssid
    Assert-NotBlank -Value $hotspotSsid -Name "hotspot.ssid"

    $hotspotSecurity = [string]$hotspotCfg.security
    if ([string]::IsNullOrWhiteSpace($hotspotSecurity)) {
        $hotspotSecurity = "WPA"
    }
    $hotspotSecurity = $hotspotSecurity.Trim().ToUpperInvariant()
    if ($hotspotSecurity -notin @("WPA", "NOPASS")) {
        throw "hotspot.security must be WPA or NOPASS."
    }

    $hotspotPassphrase = [string]$hotspotCfg.passphrase
    if ($hotspotSecurity -eq "WPA") {
        Assert-NonPlaceholderSecret -Value $hotspotPassphrase -Name "hotspot.passphrase"
        if ($hotspotPassphrase.Length -lt 8 -or $hotspotPassphrase.Length -gt 63) {
            throw "hotspot.passphrase must be between 8 and 63 characters for WPA mode."
        }
    }

    $hotspotCountry = [string]$hotspotCfg.country
    if ([string]::IsNullOrWhiteSpace($hotspotCountry)) {
        $hotspotCountry = "TZ"
    }
    $hotspotCountry = $hotspotCountry.Trim().ToUpperInvariant()

    $hotspotChannel = Get-IntOrDefault -Value $hotspotCfg.channel -Default 6
    if ($hotspotChannel -lt 1 -or $hotspotChannel -gt 13) {
        throw "hotspot.channel must be between 1 and 13."
    }

    $hotspotGatewayIp = [string]$hotspotCfg.gateway_ip
    if ([string]::IsNullOrWhiteSpace($hotspotGatewayIp)) {
        $hotspotGatewayIp = "10.55.0.1"
    }

    $hotspotDhcpStart = [string]$hotspotCfg.dhcp_start
    if ([string]::IsNullOrWhiteSpace($hotspotDhcpStart)) {
        $hotspotDhcpStart = "10.55.0.20"
    }

    $hotspotDhcpEnd = [string]$hotspotCfg.dhcp_end
    if ([string]::IsNullOrWhiteSpace($hotspotDhcpEnd)) {
        $hotspotDhcpEnd = "10.55.0.220"
    }

    $hotspotParams = @{
        interface = $hotspotInterface
        ssid = $hotspotSsid
        security = $hotspotSecurity
        passphrase = $hotspotPassphrase
        country = $hotspotCountry
        channel = $hotspotChannel
        gateway_ip = $hotspotGatewayIp
        dhcp_start = $hotspotDhcpStart
        dhcp_end = $hotspotDhcpEnd
    }
}

$resolvedApiBaseUrl = ""
if ($backendWillRun) {
    $resolvedApiBaseUrl = "http://${piHost}:$($backendParams.Port)/api/v1"
}
elseif ($agentWillRun -and -not [string]::IsNullOrWhiteSpace([string]$agentParams.BackendBaseUrl)) {
    $resolvedApiBaseUrl = [string]$agentParams.BackendBaseUrl
}
else {
    $resolvedApiBaseUrl = "http://${piHost}:8000/api/v1"
}

$fallbackPort = if ($backendWillRun) { [int]$backendParams.Port } else { 8000 }
$resolvedOrigin = Get-OriginFromApiBaseUrl -ApiBaseUrl $resolvedApiBaseUrl -FallbackHost $piHost -FallbackPort $fallbackPort
$qrHostOrigin = $resolvedOrigin
if ($hotspotEnabled) {
    $qrHostOrigin = "http://$($hotspotParams.gateway_ip):$fallbackPort"
}
$resolvedCustomerUrl = "{0}/customer-app/" -f $resolvedOrigin.TrimEnd("/")
$resolvedAdminUrl = "{0}/admin-app/" -f $resolvedOrigin.TrimEnd("/")
$resolvedQrEntryUrl = "{0}/customer-start" -f $qrHostOrigin.TrimEnd("/")

$summary = [ordered]@{
    kiosk_id = $kioskId
    profile_path = $resolvedProfilePath
    target = "$piUser@$piHost"
    validate_only = [bool]$ValidateOnly
    run_post_smoke = [bool]$RunPostSmoke
    smoke_limit = [int]$SmokeLimit
    urls = [ordered]@{
        api_base = $resolvedApiBaseUrl
        customer_app = $resolvedCustomerUrl
        admin_app = $resolvedAdminUrl
        qr_entry = $resolvedQrEntryUrl
    }
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
    hotspot = [ordered]@{
        enabled = [bool]$hotspotEnabled
        interface = if ($hotspotEnabled) { $hotspotParams.interface } else { "" }
        ssid = if ($hotspotEnabled) { $hotspotParams.ssid } else { "" }
        security = if ($hotspotEnabled) { $hotspotParams.security } else { "" }
        gateway_ip = if ($hotspotEnabled) { $hotspotParams.gateway_ip } else { "" }
    }
}

Write-Host ""
Write-Host "========== KIOSK PROFILE SUMMARY ==========" -ForegroundColor Yellow
Write-Host ($summary | ConvertTo-Json -Depth 8)

if ($ValidateOnly) {
    Write-Host ""
    Write-Host ("Planned API base: {0}" -f $resolvedApiBaseUrl) -ForegroundColor Cyan
    Write-Host ("Planned customer app URL: {0}" -f $resolvedCustomerUrl) -ForegroundColor Cyan
    Write-Host ("Planned admin app URL: {0}" -f $resolvedAdminUrl) -ForegroundColor Cyan
    Write-Host ("Planned QR entry URL: {0}" -f $resolvedQrEntryUrl) -ForegroundColor Cyan
    if ($RunPostSmoke) {
        Write-Host "Post-smoke is enabled but skipped in validation-only mode." -ForegroundColor DarkYellow
    }
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

if ($hotspotEnabled) {
    Write-Host ""
    Write-Host "========== Hotspot Setup ==========" -ForegroundColor Yellow
    $target = "$piUser@$piHost"
    $hotspotScriptPath = Join-Path $repoRoot "edge-agent\scripts\configure-hotspot-ap.sh"
    if (-not (Test-Path -LiteralPath $hotspotScriptPath)) {
        throw "Hotspot setup script not found: $hotspotScriptPath"
    }

    $remoteHotspotScript = "/home/$piUser/edge-agent/scripts/configure-hotspot-ap.sh"
    Invoke-CheckedExternal -FilePath "ssh" -Arguments @($target, "mkdir -p /home/$piUser/edge-agent/scripts") -FailureMessage "Unable to create remote hotspot script directory"
    Invoke-CheckedExternal -FilePath "scp" -Arguments @($hotspotScriptPath, "${target}:$remoteHotspotScript") -FailureMessage "Unable to upload hotspot setup script"

    $qRemoteHotspotScript = ConvertTo-BashSingleQuoted -Value $remoteHotspotScript
    $remoteParts = @(
        "chmod +x $qRemoteHotspotScript",
        "sudo $qRemoteHotspotScript --interface $(ConvertTo-BashSingleQuoted -Value ([string]$hotspotParams.interface)) --ssid $(ConvertTo-BashSingleQuoted -Value ([string]$hotspotParams.ssid)) --security $(ConvertTo-BashSingleQuoted -Value ([string]$hotspotParams.security)) --country $(ConvertTo-BashSingleQuoted -Value ([string]$hotspotParams.country)) --channel $([int]$hotspotParams.channel) --gateway-ip $(ConvertTo-BashSingleQuoted -Value ([string]$hotspotParams.gateway_ip)) --dhcp-start $(ConvertTo-BashSingleQuoted -Value ([string]$hotspotParams.dhcp_start)) --dhcp-end $(ConvertTo-BashSingleQuoted -Value ([string]$hotspotParams.dhcp_end))"
    )
    if ([string]$hotspotParams.security -eq "WPA") {
        $remoteParts[1] += " --passphrase $(ConvertTo-BashSingleQuoted -Value ([string]$hotspotParams.passphrase))"
    }
    $remoteCommand = $remoteParts -join " && "
    Invoke-CheckedExternal -FilePath "ssh" -Arguments @("-tt", $target, $remoteCommand) -FailureMessage "Hotspot setup command failed"
}
else {
    Write-Host "Skipping hotspot setup." -ForegroundColor DarkYellow
}

if ($RunPostSmoke) {
    if (-not (Test-Path -LiteralPath $postSmokeScriptPath)) {
        throw "Post-smoke script not found: $postSmokeScriptPath"
    }
    $smokeArgs = @{
        ApiBaseUrl = $resolvedApiBaseUrl
        Limit = $SmokeLimit
    }
    Invoke-StepScript -StepName "Post-Provision Admin/Customer Smoke" -ScriptPath $postSmokeScriptPath -Arguments $smokeArgs
}

Write-Host ""
Write-Host ("Kiosk provisioning completed for {0} ({1})." -f $kioskId, "$piUser@$piHost") -ForegroundColor Green
Write-Host ("Customer App: {0}" -f $resolvedCustomerUrl) -ForegroundColor Cyan
Write-Host ("Admin App: {0}" -f $resolvedAdminUrl) -ForegroundColor Cyan
Write-Host ("Customer QR Entry: {0}" -f $resolvedQrEntryUrl) -ForegroundColor Cyan
