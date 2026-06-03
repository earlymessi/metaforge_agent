# Agent 评测脚本
# 默认：规则路由 + 计划预览（无需 API Key）
# 完整：$env:RUN_LLM_BENCHMARK='1'; $env:RUN_AGENT_BENCHMARK_EXEC='1'

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host ">> 规则路由 + 计划 Tool 链（pytest）" -ForegroundColor Cyan
python -m pytest tests/test_agent_benchmark.py::test_agent_benchmark_preview_and_rule_route -v

Write-Host "`n>> 文本报告（python -m）" -ForegroundColor Cyan
python -m metaforge.eval.agent_benchmark

if ($env:RUN_LLM_BENCHMARK -eq "1") {
    Write-Host "`n>> GLM 路由评测（需 ZHIPU_API_KEY）" -ForegroundColor Yellow
    $env:LLM_ENABLED = "1"
    $env:LLM_ROUTER = "glm"
    python -m metaforge.eval.agent_benchmark
}

if ($env:RUN_AGENT_BENCHMARK_EXEC -eq "1") {
    Write-Host "`n>> 端到端执行评测" -ForegroundColor Yellow
    $env:RUN_AGENT_BENCHMARK_EXEC = "1"
    python -m pytest tests/test_agent_benchmark.py::test_agent_benchmark_run_tier -v
}
