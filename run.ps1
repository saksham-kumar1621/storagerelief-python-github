# Launch StorageRelief Python Edition
$ROOT = $PSScriptRoot
Push-Location $ROOT
try {
    Write-Host "Launching StorageRelief (Python + Edge WebView2)..." -ForegroundColor Cyan
    python main.py $args
} finally {
    Pop-Location
}
