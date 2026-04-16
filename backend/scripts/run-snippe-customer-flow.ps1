param(
    [string]$ApiBaseUrl = "http://127.0.0.1:8000/api/v1",
    [string]$DeviceCode = "pi-kiosk-001",
    [string]$Method = "tigo",
    [string]$Msisdn = "",
    [int]$Pages = 5,
    [int]$Copies = 1,
    [string]$Color = "bw",
    [double]$BwPricePerPage = 100,
    [double]$ColorPricePerPage = 300,
    [string]$Currency = "TZS",
    [string]$StorageKey = "http://192.168.0.210:8000/api/v1/test-assets/payment-success-test.pdf",
    [string]$OriginalFileName = "payment-success-test.pdf"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Msisdn)) {
    $Msisdn = Read-Host "Enter customer phone number in 255XXXXXXXXX format"
}
$Msisdn = $Msisdn.Trim()

if ($Pages -le 0 -or $Copies -le 0) {
    throw "Pages and copies must both be greater than zero."
}

Write-Host "Checking backend health at $ApiBaseUrl/health ..." -ForegroundColor Cyan
$health = Invoke-RestMethod -Method GET -Uri "$ApiBaseUrl/health"
if ($health.status -ne "ok") {
    throw "Backend is not healthy. Response: $($health | ConvertTo-Json -Depth 4)"
}
Write-Host "Backend health OK." -ForegroundColor Green

Write-Host "Creating print job ..." -ForegroundColor Cyan
$jobBody = @{
    pages = $Pages
    copies = $Copies
    color = $Color
    device_code = $DeviceCode
    bw_price_per_page = $BwPricePerPage
    color_price_per_page = $ColorPricePerPage
    currency = $Currency
    original_file_name = $OriginalFileName
    storage_key = $StorageKey
} | ConvertTo-Json

$job = Invoke-RestMethod -Method POST -Uri "$ApiBaseUrl/print-jobs" -ContentType "application/json" -Body $jobBody

if ($null -eq $job.job_id) {
    throw "Failed to create job. Response: $($job | ConvertTo-Json -Depth 6)"
}
if ([double]$job.total_cost -lt 500) {
    throw "Job total is $($job.total_cost), but Snippe minimum is 500. Increase pages/copies/prices."
}

Write-Host ("Job created: {0} | status={1} | total={2} {3}" -f $job.job_id, $job.status, $job.total_cost, $job.currency) -ForegroundColor Green
Write-Host ("Print file URL: {0}" -f $StorageKey) -ForegroundColor DarkCyan

Write-Host "Creating Snippe payment push ..." -ForegroundColor Cyan
$payBody = @{
    print_job_id = $job.job_id
    amount = $job.total_cost
    method = $Method
    msisdn = $Msisdn
    customer_first_name = "Hasnet"
    customer_last_name = "Test"
    customer_email = "test@hasnet.local"
} | ConvertTo-Json

$pay = Invoke-RestMethod -Method POST -Uri "$ApiBaseUrl/payments/create" -ContentType "application/json" -Body $payBody

Write-Host ("Payment created: {0} | status={1} | provider_request_id={2}" -f $pay.payment_id, $pay.status, $pay.provider_request_id) -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1) Approve USSD push on phone."
Write-Host "2) Watch Pi agent logs (new terminal):"
Write-Host "   ssh -tt hasnet_pi@hph-pi01.local ""sudo journalctl -u hasnet-printhub-agent -f"""
Write-Host "3) If not printing within ~1 minute, share screenshot and we debug immediately."
