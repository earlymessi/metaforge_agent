"""Agent 基准评测（路由 + 计划；执行用例默认 skip）。"""

import os

import pytest

from metaforge.eval.agent_benchmark import load_benchmark_cases, run_benchmark
from metaforge.orchestrator.session import clear_all_sessions
from metaforge.tools.load_all import load_all_tools


@pytest.fixture(scope="module", autouse=True)
def _benchmark_env():
    load_all_tools()
    clear_all_sessions()
    os.environ["LLM_ENABLED"] = "0"
    os.environ["LLM_ROUTER"] = "rule"
    yield
    clear_all_sessions()


def test_agent_benchmark_preview_and_rule_route():
    report = run_benchmark()
    assert report.failed == 0, [
        (r.case_id, r.message, r.detail) for r in report.failures()
    ]
    # 规则路由 + 计划用例应全部执行（非 skip）
    active = [r for r in report.results if not r.skipped]
    assert len(active) >= 10
    assert report.rate("route") >= 1.0
    assert report.rate("plan") >= 1.0


def test_benchmark_cases_load():
    cases = load_benchmark_cases()
    ids = {c["id"] for c in cases}
    assert "rule_plans_create" in ids
    assert "llm_kitting" in ids


@pytest.mark.skipif(
    os.getenv("RUN_AGENT_BENCHMARK_EXEC", "").strip() not in ("1", "true", "yes"),
    reason="设置 RUN_AGENT_BENCHMARK_EXEC=1 启用端到端执行评测",
)
def test_agent_benchmark_run_tier():
    from main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    def run_fn(body):
        r = client.post("/api/orchestrator/run", json=body)
        assert r.status_code == 200, r.text
        return r.json()

    cases = [c for c in load_benchmark_cases() if (c.get("tier") or "").lower() == "run"]
    report = run_benchmark(cases, run_fn=run_fn)
    assert report.failed == 0, [(r.case_id, r.detail) for r in report.failures()]
