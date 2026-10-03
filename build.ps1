# Build standalone StorageRelief.exe and StorageRelief_Setup.exe
$ErrorActionPreference = "Stop"
$ROOT = $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Building StorageRelief Executable & Windows Setup      " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

Push-Location $ROOT
try {
    # 1. Close any running instance
    Get-Process -Name "*StorageRelief*", "*storagerelief*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300

    # 2. Check PyInstaller
    Write-Host "[1/2] Compiling Standalone Portable Executable (PyInstaller)..." -ForegroundColor Cyan
    python -m PyInstaller --noconsole `
                --onefile `
                --name "StorageRelief" `
                --icon "assets/icon.ico" `
                --add-data "assets;assets" `
                --add-data "ui/web;ui/web" `
                --hidden-import "webview.platforms.winforms" `
                --hidden-import "clr" `
                --hidden-import "pythonnet" `
                --hidden-import "tkinter" `
                --hidden-import "tkinter.filedialog" `
                --clean `
                main.py

    $distExe = Join-Path $ROOT "dist\StorageRelief.exe"
    if (Test-Path $distExe) {
        $portableExe = Join-Path $ROOT "StorageRelief.exe"
        Copy-Item $distExe $portableExe -Force
        $sizeMB = [math]::Round((Get-Item $portableExe).Length / 1MB, 2)
        Write-Host ""
        Write-Host "SUCCESS: Portable Standalone Executable Created!" -ForegroundColor Green
        Write-Host ("  -> " + $portableExe + " (" + $sizeMB + " MB)") -ForegroundColor Yellow
    } else {
        throw "Build failed: dist\StorageRelief.exe was not produced."
    }

    # 3. Locate Inno Setup Compiler
    Write-Host ""
    Write-Host "[2/2] Packaging Windows Setup Installer (Inno Setup)..." -ForegroundColor Cyan
    $isccPaths = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )

    $iscc = $null
    foreach ($p in $isccPaths) {
        if ($p -and (Test-Path $p)) {
            $iscc = $p
            break
        }
    }
    if (-not $iscc) {
        $cmd = Get-Command iscc.exe -ErrorAction SilentlyContinue
        if ($cmd) { $iscc = $cmd.Source }
    }

    if ($iscc) {
        $issFile = Join-Path $ROOT "installer.iss"
        Write-Host "Compiling setup with $iscc..." -ForegroundColor DarkGray
        & $iscc $issFile
        $setupExe = Join-Path $ROOT "StorageRelief_Setup.exe"
        if (Test-Path $setupExe) {
            $setupSizeMB = [math]::Round((Get-Item $setupExe).Length / 1MB, 2)
            Write-Host "SUCCESS: Windows Setup Installer Created!" -ForegroundColor Green
            Write-Host ("  -> " + $setupExe + " (" + $setupSizeMB + " MB)") -ForegroundColor Yellow
        }
    } else {
        Write-Host "Notice: Inno Setup compiler (ISCC.exe) not found. Skipped installer creation." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "  ALL BUILDS READY FOR DISTRIBUTION & MULTI-PC TESTING!   " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "1. Portable EXE:  StorageRelief.exe" -ForegroundColor White
    Write-Host "2. Windows Setup: StorageRelief_Setup.exe" -ForegroundColor White

} finally {
    Pop-Location
}
