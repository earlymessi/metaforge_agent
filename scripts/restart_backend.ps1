# 清理 8000/8008/8010 后，在唯一端口 8008 启动后端
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
& "$root\scripts\cleanup_backend.ps1"
Start-Sleep -Seconds 2

$distIndex = "$root\tests\templates\dist\index.html"
if (-not (Test-Path $distIndex)) {
    Write-Host "Building frontend -> tests/templates/dist ..." -ForegroundColor Cyan
    Set-Location "$root\frontend"
    npm run build
    Set-Location "$root\tests"
}

Set-Location "$root\tests"
$env:PYTHONIOENCODING = "utf-8"
$env:METAFORGE_RELOAD = "0"
$env:METAFORGE_PORT = "8008"
Write-Host "Starting MetaForge on http://127.0.0.1:8008/new-ui/ (single port) ..."
python main.py
