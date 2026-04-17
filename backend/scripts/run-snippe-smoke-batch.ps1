param(
    [Parameter(Mandatory = $true)]
    [string]$Msisdn,
    [string]$ApiBaseUrl = "http://hph-pi01.local:8000/api/v1",
    [string]$PiApiBaseUrl = "http://127.0.0.1:8000/api/v1",
    [string]$PiHost = "hph-pi01.local",
    [string]$PiUser = "hasnet_pi",
    [string[]]$Methods = @("tigo", "mpesa", "airtel"),
    [int]$DelayBetweenRunsSeconds = 8,
    [int]$ReconcileLimit = 100,
    [int]$SecondReconcileDelaySeconds = 10,
    [switch]$SkipSecondReconcile,
    [string]$RemoteEnvFile = "/home/hasnet_pi/hasnet-printhub/backend/.env",
    [string]$EvidenceDir = ".\evidence",
    [string]$BatchSummaryPath = ""
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runFlowScript = Join-Path $scriptDir "run-snippe-customer-flow.ps1"
$operatorPackScript = Join-Path $scriptDir "run-daily-operator-pack.ps1"

foreach ($required in @($runFlowScript, $operatorPackScript)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required script not found: $required"
    }
}

$ApiBaseUrl = $ApiBaseUrl.TrimEnd("/")
$PiApiBaseUrl = $PiApiBaseUrl.TrimEnd("/")

if ([string]::IsNullOrWhiteSpace($EvidenceDir)) {
    throw "EvidenceDir must not be empty."
}

$fullEvidenceDir = [System.IO.Path]::GetFullPath($EvidenceDir)
if (-not (Test-Path -LiteralPath $fullEvidenceDir)) {
    New-Item -ItemType Directory -Path $fullEvidenceDir -Force | Out-Null
}

$timestamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
if ([string]::IsNullOrWhiteSpace($BatchSummaryPath)) {
    $BatchSummaryPath = Join-Path $fullEvidenceDir ("batch-smoke-" + $timestamp + ".json")
}
$BatchSummaryPath = [System.IO.Path]::GetFullPath($BatchSummaryPath)

$allowedMethods = @("tigo", "mpesa", "airtel")
$normalizedMethods = @()
foreach ($m in $Methods) {
    $raw = ("{0}" -f $m)
    foreach ($part in $raw.Split(",")) {
        $method = $part.Trim().ToLower()
        if ([string]::IsNullOrWhiteSpace($method)) {
            continue
        }

        if ($allowedMethods -notcontains $method) {
            throw "Unsupported method '$method'. Allowed: tigo, mpesa, airtel"
        }

        $normalizedMethods += $method
    }
}

if ($normalizedMethods.Count -eq 0) {
    throw "No valid methods provided."
}

Write-Host ""
Write-Host "========== SNIPPE BATCH SMOKE ==========" -ForegroundColor Yellow
Write-Host ("Msisdn: {0}" -f $Msisdn) -ForegroundColor Cyan
Write-Host ("Methods: {0}" -f ($normalizedMethods -join ", ")) -ForegroundColor Cyan
Write-Host ("API Base URL: {0}" -f $ApiBaseUrl) -ForegroundColor Cyan
Write-Host ("Evidence Dir: {0}" -f $fullEvidenceDir) -ForegroundColor Cyan

$results = @()
$runIndex = 0
$totalRuns = $normalizedMethods.Count

foreach ($method in $normalizedMethods) {
    $runIndex += 1
    Write-Host ""
    Write-Host ("--- Run {0}/{1}: method={2} ---" -f $runIndex, $totalRuns, $method) -ForegroundColor Yellow

    $flowArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $runFlowScript,
        "-ApiBaseUrl", $ApiBaseUrl,
        "-Msisdn", $Msisdn,
        "-Method", $method
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $flowOutput = & powershell @flowArgs 2>&1
    $flowExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    $flowText = ($flowOutput | ForEach-Object { "$_" }) -join "`n"
    if ($flowExitCode -ne 0) {
        $flowTail = (($flowOutput | Select-Object -Last 10) -join "`n")
        throw "run-snippe-customer-flow failed for method '$method' (exit $flowExitCode).`n$flowTail"
    }

    $refMatch = [regex]::Match($flowText, "provider_request_id=(SN[0-9A-Za-z]+)")
    if (-not $refMatch.Success) {
        throw "Could not extract provider_request_id from flow output for method '$method'."
    }
    $providerRequestId = $refMatch.Groups[1].Value
    Write-Host ("Extracted provider_request_id: {0}" -f $providerRequestId) -ForegroundColor Green

    $summaryPath = Join-Path $fullEvidenceDir ($providerRequestId + "-summary.json")
    $packArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $operatorPackScript,
        "-ProviderRequestId", $providerRequestId,
        "-PiHost", $PiHost,
        "-PiUser", $PiUser,
        "-ApiBaseUrl", $ApiBaseUrl,
        "-PiApiBaseUrl", $PiApiBaseUrl,
        "-ReconcileLimit", "$ReconcileLimit",
        "-SecondReconcileDelaySeconds", "$SecondReconcileDelaySeconds",
        "-RemoteEnvFile", $RemoteEnvFile,
        "-SaveLocalSummaryPath", $summaryPath
    )
    if ($SkipSecondReconcile) {
        $packArgs += "-SkipSecondReconcile"
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $packOutput = & powershell @packArgs 2>&1
    $packExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    $packText = ($packOutput | ForEach-Object { "$_" }) -join "`n"
    if ($packExitCode -ne 0) {
        $packTail = (($packOutput | Select-Object -Last 10) -join "`n")
        throw "run-daily-operator-pack failed for provider_request_id '$providerRequestId' (exit $packExitCode).`n$packTail"
    }

    $decisionMatches = [regex]::Matches($packText, "^\s*-\s*decision:\s*([A-Z_]+)\s*$", [System.Text.RegularExpressions.RegexOptions]::Multiline)
    $actionMatches = [regex]::Matches($packText, "^\s*-\s*action:\s*(.+?)\s*$", [System.Text.RegularExpressions.RegexOptions]::Multiline)
    $decision = if ($decisionMatches.Count -gt 0) { $decisionMatches[$decisionMatches.Count - 1].Groups[1].Value } else { "UNKNOWN" }
    $action = if ($actionMatches.Count -gt 0) { $actionMatches[$actionMatches.Count - 1].Groups[1].Value } else { "" }

    $results += [ordered]@{
        checked_at_local = (Get-Date).ToString("o")
        method = $method
        provider_request_id = $providerRequestId
        decision = $decision
        action = $action
        summary_path = $summaryPath
    }

    Write-Host ("Decision: {0}" -f $decision) -ForegroundColor Green

    if ($runIndex -lt $totalRuns -and $DelayBetweenRunsSeconds -gt 0) {
        Write-Host ("Waiting {0}s before next run ..." -f $DelayBetweenRunsSeconds) -ForegroundColor DarkCyan
        Start-Sleep -Seconds $DelayBetweenRunsSeconds
    }
}

$batchOut = [ordered]@{
    generated_at_local = (Get-Date).ToString("o")
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    msisdn = $Msisdn
    api_base_url = $ApiBaseUrl
    pi_api_base_url = $PiApiBaseUrl
    pi_host = $PiHost
    methods = $normalizedMethods
    results = $results
}

$batchParent = Split-Path -Parent $BatchSummaryPath
if (-not [string]::IsNullOrWhiteSpace($batchParent) -and -not (Test-Path -LiteralPath $batchParent)) {
    New-Item -ItemType Directory -Path $batchParent -Force | Out-Null
}

$batchOut | ConvertTo-Json -Depth 10 | Set-Content -Path $BatchSummaryPath -Encoding UTF8

Write-Host ""
Write-Host "Batch Summary" -ForegroundColor Yellow
$results | ForEach-Object {
    Write-Host ("- method={0} | ref={1} | decision={2}" -f $_.method, $_.provider_request_id, $_.decision)
}
Write-Host ("Batch JSON saved: {0}" -f $BatchSummaryPath) -ForegroundColor Green
Write-Host "Batch smoke completed." -ForegroundColor Green
