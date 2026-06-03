# GLM smoke test: scheduling / events utterances (requires ZHIPU_API_KEY in .env)

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

$env:LLM_ENABLED = "1"
$env:LLM_ROUTER = "glm"
$env:LLM_FALLBACK = "rule"

$outDir = "reports"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$jsonPath = Join-Path $outDir ("glm_smoke_{0}.json" -f $stamp)

Write-Host ">> GLM preview smoke (route + plan + trace)" -ForegroundColor Cyan
python -m metaforge.eval.glm_smoke --json $jsonPath
$code = $LASTEXITCODE

if ($env:RUN_GLM_SMOKE_EXEC -eq "1") {
    Write-Host ""
    Write-Host ">> GLM exec smoke (slow, runs solvers)" -ForegroundColor Yellow
    $execJson = Join-Path $outDir ("glm_smoke_exec_{0}.json" -f $stamp)
    python -m metaforge.eval.glm_smoke --exec --json $execJson
    if ($LASTEXITCODE -ne 0) { $code = $LASTEXITCODE }
}

if ($env:RUN_GLM_SMOKE_REACT -eq "1") {
    Write-Host ""
    Write-Host ">> GLM ReAct preview smoke" -ForegroundColor Yellow
    $reactJson = Join-Path $outDir ("glm_smoke_react_{0}.json" -f $stamp)
    python -m metaforge.eval.glm_smoke --react --json $reactJson
}

exit $code
