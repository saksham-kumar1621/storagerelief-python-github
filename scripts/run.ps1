# Launch StorageRelief Python Edition
$ROOT = if (Test-Path (Join-Path $PSScriptRoot "main.py")) { $PSScriptRoot } else { Split-Path -Parent $PSScriptRoot }
Push-Location $ROOT
try {
    Write-Host "Launching StorageRelief (Python + Edge WebView2)..." -ForegroundColor Cyan
    python main.py $args
} finally {
    Pop-Location
}
