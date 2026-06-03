"""Agent LLM Plan 测试。"""

import os
from unittest.mock import patch

import pytest

from metaforge.agents.base import AgentRequest
from metaforge.agents.scheduling import SchedulingAgentRunner
from metaforge.orchestrator.llm_plan import (
    llm_plan_enabled_for,
    normalize_plan_steps,
    resolve_agent_plan_steps,
)


def test_normalize_plan_steps_valid():
    raw = {
        "steps": [
            {"step_id": "s1", "tool": "scheduling.parse_intent", "params": {"message": "x"}},
            {"step_id": "s2", "tool": "scheduling.run", "params": {}},
        ]
    }
    steps = normalize_plan_steps(raw, ["scheduling.parse_intent", "scheduling.run"])
    assert len(steps) == 2
    assert steps[1].tool == "scheduling.run"


def test_normalize_rejects_unknown_tool():
    with pytest.raises(ValueError, match="not allowed"):
        normalize_plan_steps({"steps": [{"tool": "hack.tool", "params": {}}]}, ["scheduling.run"])


@patch("metaforge.orchestrator.llm_plan.build_plan_with_llm")
def test_resolve_agent_plan_llm(mock_llm):
    from metaforge.agents.base import PlanStep

    mock_llm.return_value = [PlanStep("s1", "scheduling.run", {})]
    with patch.dict("os.environ", {"LLM_ENABLED": "1", "ZHIPU_API_KEY": "k", "LLM_PLAN_ENABLED": "1"}):
        steps, planner = resolve_agent_plan_steps(
            agent_id="scheduling",
            name_zh="智能排程",
            allowed_tools=["scheduling.parse_intent", "scheduling.run"],
            message="排程",
            params={},
            rule_builder=lambda: [PlanStep("s1", "scheduling.parse_intent", {})],
        )
    assert planner == "llm"
    assert steps[0].tool == "scheduling.run"


def test_scheduling_agent_rule_plan_when_llm_off():
    os.environ["LLM_ENABLED"] = "0"
    agent = SchedulingAgentRunner()
    steps = agent.build_plan(AgentRequest(message="交付优先，用禁忌搜索排程", params={}))
    assert len(steps) == 2
    assert steps[0].tool == "scheduling.parse_intent"
    assert agent._plan_planner == "rule"


@patch("metaforge.orchestrator.llm_plan.build_plan_with_llm", side_effect=RuntimeError("fail"))
def test_scheduling_agent_plan_fallback(mock_llm):
    with patch.dict(
        "os.environ",
        {"LLM_ENABLED": "1", "ZHIPU_API_KEY": "k", "LLM_PLAN_ENABLED": "1", "LLM_FALLBACK": "rule"},
    ):
        agent = SchedulingAgentRunner()
        steps = agent.build_plan(AgentRequest(message="交付优先，用禁忌搜索排程"))
    assert agent._plan_planner == "rule_fallback"
    assert steps[0].tool == "scheduling.parse_intent"
