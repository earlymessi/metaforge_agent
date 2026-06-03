"""L2 GLM Preview 自动化（需 ZHIPU_API_KEY + RUN_GLM_PREVIEW=1）。"""

import os

import pytest

from metaforge.eval.agent_e2e import load_cases, run_l2_case, run_suite
from metaforge.orchestrator.session import clear_all_sessions
from metaforge.tools.load_all import load_all_tools


@pytest.fixture(scope="module", autouse=True)
def _e2e_env():
    load_all_tools()
    clear_all_sessions()
    yield
    clear_all_sessions()


@pytest.mark.skipif(
    os.getenv("RUN_GLM_PREVIEW", "").strip().lower() not in ("1", "true", "yes"),
    reason="设置 RUN_GLM_PREVIEW=1 启用 L2 GLM Preview 评测",
)
@pytest.mark.skipif(
    not (os.getenv("ZHIPU_API_KEY") or "").strip(),
    reason="未配置 ZHIPU_API_KEY",
)
def test_l2_preview_suite_pass_rate():
    report = run_suite("preview", verbose=False)
    assert report.skipped == 0, [(r.case_id, r.skip_reason) for r in report.results if r.skipped]
    assert report.rate() >= 0.85, [
        (r.case_id, r.message, r.detail) for r in report.failures()
    ]


@pytest.mark.skipif(
    os.getenv("RUN_GLM_PREVIEW", "").strip().lower() not in ("1", "true", "yes"),
    reason="设置 RUN_GLM_PREVIEW=1",
)
@pytest.mark.skipif(
    not (os.getenv("ZHIPU_API_KEY") or "").strip(),
    reason="未配置 ZHIPU_API_KEY",
)
@pytest.mark.parametrize(
    "case",
    [c for c in load_cases("preview", tags=["adversarial"])],
    ids=lambda c: c["id"],
)
def test_l2_adversarial_routing(case):
    from metaforge.eval.agent_e2e import _apply_llm_env

    _apply_llm_env()
    result = run_l2_case(case)
    assert result.ok, (result.message, result.detail)
