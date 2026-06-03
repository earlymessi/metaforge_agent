"""L3 Agent 端到端执行自动化（需 ZHIPU_API_KEY + RUN_GLM_EXEC=1）。"""

import os

import pytest
from fastapi.testclient import TestClient

from metaforge.eval.agent_e2e import load_cases, run_suite
from metaforge.orchestrator.session import clear_all_sessions
from metaforge.tools.load_all import load_all_tools


@pytest.fixture(scope="module")
def run_fn():
    os.environ.setdefault("SESSION_STORE", "memory")
    load_all_tools()
    clear_all_sessions()
    from main import app

    def _run(body):
        with TestClient(app) as client:
            r = client.post("/api/orchestrator/run", json=body)
        assert r.status_code == 200, r.text
        return r.json()

    yield _run
    clear_all_sessions()


@pytest.mark.skipif(
    os.getenv("RUN_GLM_EXEC", "").strip().lower() not in ("1", "true", "yes"),
    reason="设置 RUN_GLM_EXEC=1 启用 L3 端到端评测",
)
@pytest.mark.skipif(
    not (os.getenv("ZHIPU_API_KEY") or "").strip(),
    reason="未配置 ZHIPU_API_KEY",
)
def test_l3_exec_core_agents(run_fn):
    """scheduling + events + kitting + whatif 核心用例（排除 mongo/slow）。"""
    tags = ["scheduling", "events", "kitting", "whatif", "multi_turn", "commitment"]
    cases = [
        c
        for c in load_cases("exec")
        if any(t in (c.get("tags") or []) for t in tags)
        and "mongo" not in (c.get("tags") or [])
        and "slow" not in (c.get("tags") or [])
    ]
    report = run_suite("exec", cases=cases, run_fn=run_fn, verbose=False)
    skipped = [(r.case_id, r.skip_reason) for r in report.results if r.skipped]
    assert report.skipped == 0, skipped
    assert report.rate() >= 0.80, [
        (r.case_id, r.message, r.detail) for r in report.failures()
    ]


@pytest.mark.skipif(
    os.getenv("RUN_GLM_EXEC", "").strip().lower() not in ("1", "true", "yes"),
    reason="设置 RUN_GLM_EXEC=1",
)
@pytest.mark.skipif(
    not (os.getenv("ZHIPU_API_KEY") or "").strip(),
    reason="未配置 ZHIPU_API_KEY",
)
def test_l3_exec_deterministic_scheduling(run_fn):
    cases = [c for c in load_cases("exec") if "deterministic" in (c.get("tags") or [])]
    assert cases, "l3_exec.yaml 需含 tags: deterministic 的排程对照用例"
    report = run_suite("exec", cases=cases, run_fn=run_fn, verbose=False)
    assert report.failed == 0, [(r.case_id, r.message) for r in report.failures()]
