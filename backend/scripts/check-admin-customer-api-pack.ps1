param(
    [string]$ApiBaseUrl = "http://hph-pi01.local:8000/api/v1",
    [int]$Limit = 5,
    [string]$JobId = ""
)

$ErrorActionPreference = "Stop"

if ($Limit -lt 1 -or $Limit -gt 200) {
    throw "Limit must be between 1 and 200."
}

$ApiBaseUrl = $ApiBaseUrl.TrimEnd("/")

Write-Host ""
Write-Host "========== ADMIN/CUSTOMER API SMOKE ==========" -ForegroundColor Yellow
Write-Host ("ApiBaseUrl: {0}" -f $ApiBaseUrl) -ForegroundColor Cyan

$devicesUrl = "$ApiBaseUrl/admin/devices?include_inactive=false"
$alertsUrl = "$ApiBaseUrl/alerts?limit=$Limit"
$paymentsUrl = "$ApiBaseUrl/admin/payments?limit=$Limit"
$reportUrl = "$ApiBaseUrl/admin/reports/today"

Write-Host ""
Write-Host ("GET {0}" -f $devicesUrl) -ForegroundColor DarkCyan
$devices = Invoke-RestMethod -Method GET -Uri $devicesUrl
Write-Host ("- devices_count: {0}" -f (@($devices.items).Count))

Write-Host ""
Write-Host ("GET {0}" -f $alertsUrl) -ForegroundColor DarkCyan
$alerts = Invoke-RestMethod -Method GET -Uri $alertsUrl
Write-Host ("- alerts_count: {0}" -f (@($alerts.items).Count))

Write-Host ""
Write-Host ("GET {0}" -f $paymentsUrl) -ForegroundColor DarkCyan
$payments = Invoke-RestMethod -Method GET -Uri $paymentsUrl
Write-Host ("- payments_count: {0}" -f (@($payments.items).Count))

Write-Host ""
Write-Host ("GET {0}" -f $reportUrl) -ForegroundColor DarkCyan
$report = Invoke-RestMethod -Method GET -Uri $reportUrl
Write-Host ("- today_confirmed_payments: {0}" -f $report.payments.confirmed)
Write-Host ("- today_confirmed_amount: {0} {1}" -f $report.payments.confirmed_amount, "TZS")
Write-Host ("- today_printed_jobs: {0}" -f $report.jobs.printed)
Write-Host ("- active_devices: {0}" -f $report.devices.active)

if (-not [string]::IsNullOrWhiteSpace($JobId)) {
    $parsedJob = $null
    try {
        $parsedJob = [Guid]::Parse($JobId.Trim())
    }
    catch {
        throw "JobId must be a valid UUID."
    }

    $jobUrl = "$ApiBaseUrl/print-jobs/$parsedJob/customer-status"
    Write-Host ""
    Write-Host ("GET {0}" -f $jobUrl) -ForegroundColor DarkCyan
    $jobStatus = Invoke-RestMethod -Method GET -Uri $jobUrl
    Write-Host ("- customer_stage: {0}" -f $jobStatus.stage)
    Write-Host ("- customer_message: {0}" -f $jobStatus.message)
    Write-Host ("- customer_next_action: {0}" -f $jobStatus.next_action)
}

Write-Host ""
Write-Host "Smoke Summary" -ForegroundColor Green
Write-Host ("- /admin/devices: OK ({0} items)" -f (@($devices.items).Count))
Write-Host ("- /alerts: OK ({0} items)" -f (@($alerts.items).Count))
Write-Host ("- /admin/payments: OK ({0} items)" -f (@($payments.items).Count))
Write-Host "- /admin/reports/today: OK"
if (-not [string]::IsNullOrWhiteSpace($JobId)) {
    Write-Host "- /print-jobs/{job_id}/customer-status: OK"
}
Write-Host "Admin/customer API smoke completed." -ForegroundColor Green
