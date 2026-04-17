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
try {
    $snapshot = Invoke-RestMethod -Method GET -Uri $uri
}
catch {
    $response = $_.Exception.Response
    if ($response -and [int]$response.StatusCode -eq 404) {
        Write-Host ""
        Write-Host "Endpoint not found on target API (404)." -ForegroundColor Red
        Write-Host "This usually means Pi backend is on older code and missing /payments/by-provider-ref/{provider_request_id}." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Next step:" -ForegroundColor Cyan
        Write-Host "Run deploy script from backend folder:" -ForegroundColor Cyan
        Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\deploy-payment-snapshot-hotfix-to-pi.ps1 -PiHost hph-pi01.local -VerifyProviderRequestId $ProviderRequestId" -ForegroundColor Cyan
        exit 2
    }

    throw
}

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
