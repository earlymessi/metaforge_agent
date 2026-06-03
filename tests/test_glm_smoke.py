"""GLM 联调脚本结构测试（不调用真实 API）。"""

import os
from unittest.mock import patch

import pytest

from metaforge.eval.glm_smoke import SMOKE_CASES, format_report, run_preview_case


@pytest.fixture(autouse=True)
def _rule_env():
    os.environ["LLM_ENABLED"] = "0"
    os.environ["LLM_ROUTER"] = "rule"
    yield


def test_smoke_cases_cover_domains():
    domains = {c.domain for c in SMOKE_CASES}
    assert "scheduling" in domains
    assert "events" in domains
    assert len([c for c in SMOKE_CASES if c.domain == "scheduling"]) >= 5
    assert len([c for c in SMOKE_CASES if c.domain == "events"]) >= 5


@patch("metaforge.orchestrator.preview.build_orchestrator_preview")
def test_run_preview_case_extracts_tools(mock_preview):
    from metaforge.eval.glm_smoke import SmokeCase

    mock_preview.return_value = {
        "agent_id": "scheduling",
        "router_planner": "explicit",
        "plan_planner": "rule",
        "route": {"router": "explicit", "intent": "schedule", "agent_id": "scheduling"},
        "trace": [
            {"phase": "route", "lines": ["用户指定意图：排程"]},
            {
                "phase": "plan",
                "planner": "rule",
                "steps": [{"tool": "scheduling.parse_intent"}, {"tool": "scheduling.run"}],
                "lines": ["s1 scheduling.parse_intent"],
            },
        ],
    }
    case = SmokeCase("t", "排程", "scheduling", "scheduling", intent="schedule")
    r = run_preview_case(case)
    assert r.ok
    assert r.tools == ["scheduling.parse_intent", "scheduling.run"]
    assert r.plan_planner == "rule"


def test_format_report_markdown():
    from metaforge.eval.glm_smoke import SmokeResult

    text = format_report(
        [
            SmokeResult(
                "sch_x",
                "测试",
                "scheduling",
                True,
                agent_id="scheduling",
                router="llm",
                plan_planner="llm",
                tools=["scheduling.run"],
            )
        ],
        exec_mode=False,
    )
    assert "MetaForge GLM" in text
    assert "sch_x" in text
