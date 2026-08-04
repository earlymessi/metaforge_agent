# MetaForge one-click start (Windows PowerShell 5.1+ / pwsh)
# Usage:
#   .\scripts\start_metaforge.ps1
#   .\scripts\start_metaforge.ps1 -Rebuild
#   .\scripts\start_metaforge.ps1 -Install
#   .\scripts\start_metaforge.ps1 -NoBrowser
#   .\start.bat

param(
    [switch]$Rebuild,
    [switch]$Install,
    [switch]$NoBrowser,
    [switch]$SkipCleanup
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if ($env:METAFORGE_HOST) { $mfHost = $env:METAFORGE_HOST } else { $mfHost = "127.0.0.1" }
if ($env:METAFORGE_PORT) { $mfPort = $env:METAFORGE_PORT } else { $mfPort = "8008" }

$entryUrl = "http://" + $mfHost + ":" + $mfPort + "/go"
$dashUrl = "http://" + $mfHost + ":" + $mfPort + "/new-ui/dashboard"
$apsUrl = "http://" + $mfHost + ":" + $mfPort + "/new-ui/aps"
$distIndex = Join-Path $root "tests\templates\dist\index.html"

function Write-Step {
    param([string]$Num, [string]$Message)
    Write-Host ""
    Write-Host ("[" + $Num + "] " + $Message) -ForegroundColor Cyan
}

Set-Location $root
Write-Host "========================================" -ForegroundColor Green
Write-Host " MetaForge start" -ForegroundColor Green
Write-Host (" Root: " + $root) -ForegroundColor Green
Write-Host (" Open: " + $entryUrl) -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

# 1) MongoDB
Write-Step "1/5" "MongoDB service"
$mongo = Get-Service -Name "MongoDB" -ErrorAction SilentlyContinue
if ($null -eq $mongo) {
    Write-Host "  WARN: MongoDB Windows service not found (need port 27017)" -ForegroundColor Yellow
}
elseif ($mongo.Status -ne "Running") {
    $started = $false
    try {
        Start-Service -Name "MongoDB"
        Start-Sleep -Seconds 2
        $started = $true
    }
    catch {
        Write-Host ("  WARN: cannot start MongoDB (try Admin PowerShell): " + $_.Exception.Message) -ForegroundColor Yellow
    }
    if ($started) {
        Write-Host "  MongoDB started" -ForegroundColor Green
    }
}
else {
    Write-Host "  MongoDB already running" -ForegroundColor Green
}

# 2) Cleanup old backend
if (-not $SkipCleanup) {
    Write-Step "2/5" "Cleanup old backend (8000/8008/8010)"
    & (Join-Path $PSScriptRoot "cleanup_backend.ps1")
    Start-Sleep -Seconds 1
}
else {
    Write-Step "2/5" "Skip cleanup (-SkipCleanup)"
}

# 3) Optional install
Write-Step "3/5" "Dependencies"
if ($Install) {
    Write-Host "  pip install -e ."
    pip install -e .
    if ($LASTEXITCODE -ne 0) { throw "pip install -e . failed" }
    $pkg = Join-Path $root "frontend\package.json"
    if (Test-Path $pkg) {
        Write-Host "  npm install (frontend)"
        Push-Location (Join-Path $root "frontend")
        try {
            npm install
            if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
        }
        finally {
            Pop-Location
        }
    }
}
else {
    Write-Host "  skip install (use -Install when needed)" -ForegroundColor DarkGray
}

# 4) Frontend build
Write-Step "4/5" "Frontend dist"
$needBuild = $Rebuild -or -not (Test-Path $distIndex)
if ($needBuild) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js/npm required to build frontend, or prepare tests/templates/dist/"
    }
    Write-Host "  npm run build -> tests/templates/dist/"
    Push-Location (Join-Path $root "frontend")
    try {
        if ($Install -or -not (Test-Path "node_modules")) {
            npm install
            if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
        }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    }
    finally {
        Pop-Location
    }
    if (-not (Test-Path $distIndex)) {
        throw ("build finished but missing: " + $distIndex)
    }
    Write-Host "  frontend build ok" -ForegroundColor Green
}
else {
    Write-Host "  dist exists, skip build (use -Rebuild to force)" -ForegroundColor DarkGray
}

# 5) Start backend
Write-Step "5/5" "Start backend tests/main.py"
$env:PYTHONIOENCODING = "utf-8"
$env:METAFORGE_RELOAD = "0"
if (-not $env:METAFORGE_PORT) { $env:METAFORGE_PORT = "8008" }
if (-not $env:METAFORGE_HOST) { $env:METAFORGE_HOST = "127.0.0.1" }

if (-not $NoBrowser) {
    $urlForJob = $entryUrl
    Start-Job -ScriptBlock {
        param($url)
        Start-Sleep -Seconds 3
        $opened = $false
        for ($i = 0; $i -lt 30; $i++) {
            try {
                $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -MaximumRedirection 5
                if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {
                    Start-Process $url
                    $opened = $true
                    break
                }
            }
            catch {
                Start-Sleep -Seconds 1
            }
        }
        if (-not $opened) {
            Start-Process $url
        }
    } -ArgumentList $urlForJob | Out-Null
    Write-Host ("  browser will open: " + $entryUrl) -ForegroundColor Green
}

Write-Host ""
Write-Host "Backend logs below (Ctrl+C to stop)..." -ForegroundColor Yellow
Write-Host ("Dashboard: " + $dashUrl)
Write-Host ("APS:       " + $apsUrl)
Write-Host ""

Set-Location (Join-Path $root "tests")
python .\main.py
