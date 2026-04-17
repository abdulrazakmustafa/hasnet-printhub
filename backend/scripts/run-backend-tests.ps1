param(
    [string]$PytestArgs = ""
)

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$venvPython = [System.IO.Path]::GetFullPath($venvPython)

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment python not found at $venvPython. Create backend\.venv first."
}

$baseArgs = @(
    "-m", "pytest",
    "-q",
    "tests",
    "-p", "no:cacheprovider"
)

if (-not [string]::IsNullOrWhiteSpace($PytestArgs)) {
    $baseArgs += $PytestArgs.Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)
}

Write-Host ""
Write-Host "========== BACKEND TEST PACK ==========" -ForegroundColor Yellow
Write-Host ("Python: {0}" -f $venvPython) -ForegroundColor Cyan
Write-Host ("Command: {0} {1}" -f $venvPython, ($baseArgs -join " ")) -ForegroundColor DarkCyan
Write-Host ""

& $venvPython @baseArgs

if ($LASTEXITCODE -ne 0) {
    throw "Backend tests failed with exit code $LASTEXITCODE."
}

Write-Host ""
Write-Host "Backend tests passed." -ForegroundColor Green
