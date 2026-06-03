# Agent GLM E2E: L2 Preview + L3 Exec (requires ZHIPU_API_KEY in .env)
param(
    [switch]$Preview,
    [switch]$Exec,
    [switch]$Full,
    [string]$Tags = "",
    [int]$Limit = 0
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not $env:ZHIPU_API_KEY) {
    if (Test-Path ".env") {
        Get-Content ".env" | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
                $name = $matches[1].Trim()
                $val = $matches[2].Trim().Trim('"').Trim("'")
                [Environment]::SetEnvironmentVariable($name, $val, "Process")
            }
        }
    }
}

if (-not $env:ZHIPU_API_KEY) {
    Write-Host "Missing ZHIPU_API_KEY. Copy .env.example to .env and set your key." -ForegroundColor Red
    exit 2
}

$outDir = "reports"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
function Invoke-AgentE2e {
    param(
        [string]$Tier,
        [string]$JsonPath
    )
    $pyArgs = @(
        "-m", "metaforge.eval.agent_e2e",
        "--tier", $Tier,
        "--json", $JsonPath
    )
    if ($Tags) {
        $pyArgs += @("--tags", $Tags)
    }
    if ($Limit -gt 0) {
        $pyArgs += @("--limit", "$Limit")
    }
    python @pyArgs
}

$runPreview = $Preview -or $Full -or (-not $Preview -and -not $Exec -and -not $Full)
$runExec = $Exec -or $Full
$env:SESSION_STORE = "memory"
$env:AGENT_E2E = "1"
$env:AGENT_E2E_MONGO = "1"
$env:AGENT_E2E_SLOW = "1"
$testsPath = Join-Path $PSScriptRoot "..\tests" | Resolve-Path
$env:PYTHONPATH = "$testsPath;$env:PYTHONPATH"
$code = 0

if ($runPreview) {
    $env:RUN_GLM_PREVIEW = "1"
    $jsonPath = Join-Path $outDir ("agent_e2e_l2_{0}.json" -f $stamp)
    Write-Host ">> L2 GLM Preview (route + plan + parse)" -ForegroundColor Cyan
    Invoke-AgentE2e -Tier preview -JsonPath $jsonPath
    if ($LASTEXITCODE -ne 0) { $code = $LASTEXITCODE }
}

if ($runExec) {
    $env:RUN_GLM_EXEC = "1"
    $jsonPath = Join-Path $outDir ("agent_e2e_l3_{0}.json" -f $stamp)
    Write-Host ""
    Write-Host ">> L3 Agent Exec (full tool run)" -ForegroundColor Yellow
    Invoke-AgentE2e -Tier exec -JsonPath $jsonPath
    if ($LASTEXITCODE -ne 0) { $code = $LASTEXITCODE }
}

exit $code
