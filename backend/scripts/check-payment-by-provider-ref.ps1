param(
    [Parameter(Mandatory = $true)]
    [string]$ProviderRequestId,
    [string]$ApiBaseUrl = "http://hph-pi01.local:8000/api/v1"
)

$ErrorActionPreference = "Stop"

if (-not $ProviderRequestId.Trim().StartsWith("SN")) {
    throw "ProviderRequestId must start with 'SN'. Got: $ProviderRequestId"
}

$ApiBaseUrl = $ApiBaseUrl.TrimEnd("/")
$encodedRef = [System.Uri]::EscapeDataString($ProviderRequestId.Trim())
$uri = "$ApiBaseUrl/payments/by-provider-ref/$encodedRef"

Write-Host ("Fetching payment snapshot from: {0}" -f $uri) -ForegroundColor Cyan
$snapshot = Invoke-RestMethod -Method GET -Uri $uri

Write-Host ""
Write-Host "Payment Snapshot" -ForegroundColor Yellow
Write-Host ("- provider_request_id: {0}" -f $snapshot.provider_request_id)
Write-Host ("- payment_status: {0}" -f $snapshot.payment_status)
Write-Host ("- print_job_status: {0}" -f $snapshot.print_job_status)
Write-Host ("- print_job_payment_status: {0}" -f $snapshot.print_job_payment_status)
Write-Host ("- device_code: {0}" -f $snapshot.device_code)
Write-Host ("- device_printer_status: {0}" -f $snapshot.device_printer_status)

Write-Host ""
$snapshot | ConvertTo-Json -Depth 8
