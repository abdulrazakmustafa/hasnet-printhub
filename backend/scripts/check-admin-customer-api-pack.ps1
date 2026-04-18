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
$pendingIncidentsUrl = "$ApiBaseUrl/admin/payments/pending-incidents?limit=$Limit"
$pricingUrl = "$ApiBaseUrl/admin/pricing"
$dashboardSnapshotUrl = "$ApiBaseUrl/admin/dashboard/snapshot?recent_payments_limit=$Limit&pending_incidents_limit=$Limit"
$reportUrl = "$ApiBaseUrl/admin/reports/today"
$customerExperienceUrl = "$ApiBaseUrl/admin/customer-experience"
$customerAvailabilityUrl = "$ApiBaseUrl/admin/customer-availability"
$customerConfigUrl = "$ApiBaseUrl/print-jobs/customer-config"
$refundsUrl = "$ApiBaseUrl/admin/refunds"

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
Write-Host ("GET {0}" -f $pendingIncidentsUrl) -ForegroundColor DarkCyan
$pendingIncidents = Invoke-RestMethod -Method GET -Uri $pendingIncidentsUrl
Write-Host ("- pending_incidents_count: {0}" -f (@($pendingIncidents.items).Count))
Write-Host ("- escalated_incidents_count: {0}" -f $pendingIncidents.escalated_count)

Write-Host ""
Write-Host ("GET {0}" -f $pricingUrl) -ForegroundColor DarkCyan
$pricing = Invoke-RestMethod -Method GET -Uri $pricingUrl
Write-Host ("- bw_price_per_page: {0}" -f $pricing.bw_price_per_page)
Write-Host ("- color_price_per_page: {0}" -f $pricing.color_price_per_page)
Write-Host ("- pricing_currency: {0}" -f $pricing.currency)

Write-Host ""
Write-Host ("GET {0}" -f $dashboardSnapshotUrl) -ForegroundColor DarkCyan
$dashboardSnapshot = Invoke-RestMethod -Method GET -Uri $dashboardSnapshotUrl
Write-Host ("- dashboard_confirmed_payments_today: {0}" -f $dashboardSnapshot.kpis.confirmed_payments_today)
Write-Host ("- dashboard_printed_jobs_today: {0}" -f $dashboardSnapshot.kpis.printed_jobs_today)
Write-Host ("- dashboard_pending_incidents: {0}" -f $dashboardSnapshot.kpis.pending_incidents)
Write-Host ("- dashboard_recent_payments_count: {0}" -f $dashboardSnapshot.recent_payments.count)

Write-Host ""
Write-Host ("GET {0}" -f $reportUrl) -ForegroundColor DarkCyan
$report = Invoke-RestMethod -Method GET -Uri $reportUrl
Write-Host ("- today_confirmed_payments: {0}" -f $report.payments.confirmed)
Write-Host ("- today_confirmed_amount: {0} {1}" -f $report.payments.confirmed_amount, "TZS")
Write-Host ("- today_printed_jobs: {0}" -f $report.jobs.printed)
Write-Host ("- active_devices: {0}" -f $report.devices.active)

Write-Host ""
Write-Host ("GET {0}" -f $customerExperienceUrl) -ForegroundColor DarkCyan
$customerExperience = Invoke-RestMethod -Method GET -Uri $customerExperienceUrl
Write-Host ("- active_device_code: {0}" -f $customerExperience.active_device_code)

Write-Host ""
Write-Host ("GET {0}" -f $customerAvailabilityUrl) -ForegroundColor DarkCyan
$customerAvailability = Invoke-RestMethod -Method GET -Uri $customerAvailabilityUrl
Write-Host ("- customer_can_upload: {0}" -f $customerAvailability.availability.can_upload)
Write-Host ("- customer_can_pay: {0}" -f $customerAvailability.availability.can_pay)
Write-Host ("- customer_reason_code: {0}" -f $customerAvailability.availability.reason_code)

Write-Host ""
Write-Host ("GET {0}" -f $customerConfigUrl) -ForegroundColor DarkCyan
$customerConfig = Invoke-RestMethod -Method GET -Uri $customerConfigUrl
Write-Host ("- customer_config_contract: {0}" -f $customerConfig.contract_version)

if (-not [string]::IsNullOrWhiteSpace([string]$customerAvailability.device_code)) {
    $qrPackUrl = "$ApiBaseUrl/admin/devices/$($customerAvailability.device_code)/qr-pack"
    Write-Host ""
    Write-Host ("GET {0}" -f $qrPackUrl) -ForegroundColor DarkCyan
    $qrPack = Invoke-RestMethod -Method GET -Uri $qrPackUrl
    Write-Host ("- qr_entry_url: {0}" -f $qrPack.entry_url)
}

Write-Host ""
Write-Host ("GET {0}" -f $refundsUrl) -ForegroundColor DarkCyan
$refunds = Invoke-RestMethod -Method GET -Uri $refundsUrl
Write-Host ("- refunds_count: {0}" -f $refunds.count)

if (-not [string]::IsNullOrWhiteSpace($JobId)) {
    $parsedJob = $null
    try {
        $parsedJob = [Guid]::Parse($JobId.Trim())
    }
    catch {
        throw "JobId must be a valid UUID."
    }

    $jobUrl = "$ApiBaseUrl/print-jobs/$parsedJob/customer-status"
    $receiptUrl = "$ApiBaseUrl/print-jobs/$parsedJob/customer-receipt"
    Write-Host ""
    Write-Host ("GET {0}" -f $jobUrl) -ForegroundColor DarkCyan
    $jobStatus = Invoke-RestMethod -Method GET -Uri $jobUrl
    Write-Host ("- customer_contract: {0}" -f $jobStatus.contract_version)
    Write-Host ("- customer_stage: {0}" -f $jobStatus.stage)
    Write-Host ("- customer_message: {0}" -f $jobStatus.message)
    Write-Host ("- customer_next_action: {0}" -f $jobStatus.next_action)
    Write-Host ("- customer_timeline_events: {0}" -f (@($jobStatus.timeline).Count))

    Write-Host ""
    Write-Host ("GET {0}" -f $receiptUrl) -ForegroundColor DarkCyan
    $jobReceipt = Invoke-RestMethod -Method GET -Uri $receiptUrl
    Write-Host ("- receipt_contract: {0}" -f $jobReceipt.contract_version)
    Write-Host ("- receipt_headline: {0}" -f $jobReceipt.headline)
    Write-Host ("- receipt_stage: {0}" -f $jobReceipt.stage)
}

Write-Host ""
Write-Host "Smoke Summary" -ForegroundColor Green
Write-Host ("- /admin/devices: OK ({0} items)" -f (@($devices.items).Count))
Write-Host ("- /alerts: OK ({0} items)" -f (@($alerts.items).Count))
Write-Host ("- /admin/payments: OK ({0} items)" -f (@($payments.items).Count))
Write-Host ("- /admin/payments/pending-incidents: OK ({0} items)" -f (@($pendingIncidents.items).Count))
Write-Host "- /admin/pricing: OK"
Write-Host "- /admin/dashboard/snapshot: OK"
Write-Host "- /admin/reports/today: OK"
Write-Host "- /admin/customer-experience: OK"
Write-Host "- /admin/customer-availability: OK"
Write-Host "- /print-jobs/customer-config: OK"
Write-Host "- /admin/devices/{device_code}/qr-pack: OK"
Write-Host "- /admin/refunds: OK"
if (-not [string]::IsNullOrWhiteSpace($JobId)) {
    Write-Host "- /print-jobs/{job_id}/customer-status: OK"
    Write-Host "- /print-jobs/{job_id}/customer-receipt: OK"
}
Write-Host "Admin/customer API smoke completed." -ForegroundColor Green
