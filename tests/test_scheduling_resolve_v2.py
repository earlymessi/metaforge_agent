"""排程意图解析 v2：澄清、动态 plan、confidence。"""

import os

import pytest

from metaforge.agents.base import AgentRequest
from metaforge.agents.scheduling import SchedulingAgentRunner
from metaforge.scheduling.context import ContextManager
from metaforge.scheduling.intent_types import ScheduleIntentType
from metaforge.scheduling.resolve_intent import resolve_schedule_intent
from metaforge.tools.load_all import load_all_tools


@pytest.fixture(autouse=True)
def _clear_llm_env():
    os.environ.pop("LLM_ENABLED", None)
    os.environ.pop("ZHIPU_API_KEY", None)
    ContextManager._store.clear()
    yield
    ContextManager._store.clear()


def test_resolve_vague_message_clarification():
    result = resolve_schedule_intent(
        {"message": "帮我排一下"},
        session_id="sess-clarify",
    )
    assert result["intent_type"] == ScheduleIntentType.CLARIFICATION.value
    assert result.get("clarification_question")
    assert ContextManager.get_pending("sess-clarify") is not None


def test_resolve_pending_merge_delivery_no_material():
    resolve_schedule_intent({"message": "帮我排一下"}, session_id="sess-merge")
    result = resolve_schedule_intent(
        {"message": "交付优先，不考虑物料"},
        session_id="sess-merge",
    )
    assert result["intent_type"] == ScheduleIntentType.RUN_SCHEDULE.value
    assert result["strategy_id"] == "delivery"
    assert result["enforce_material"] is False
    assert ContextManager.get_pending("sess-merge") is None


def test_resolve_list_solvers():
    result = resolve_schedule_intent({"message": "有哪些算法"})
    assert result["intent_type"] == ScheduleIntentType.LIST_SOLVERS.value
    assert result["confidence"] >= 0.95


def test_scheduling_agent_plan_clarification():
    load_all_tools()
    agent = SchedulingAgentRunner()
    req = AgentRequest(message="帮我排一下", context={"session_id": "plan-clar"})
    steps = agent.build_rule_plan(req)
    assert len(steps) == 1
    assert steps[0].tool == "scheduling.ask_clarification"


def test_scheduling_agent_plan_list_catalog():
    load_all_tools()
    agent = SchedulingAgentRunner()
    req = AgentRequest(message="有哪些算法")
    steps = agent.build_rule_plan(req)
    assert steps[0].tool == "scheduling.list_catalog"


def test_scheduling_agent_run_pending_clarification():
    load_all_tools()
    agent = SchedulingAgentRunner()
    req = AgentRequest(message="帮我排一下", context={"session_id": "run-clar"})
    resp = agent.run(req)
    assert resp.status == "pending_clarification"
    assert resp.ui_action is None
    assert "交期" in resp.summary_zh or "物料" in resp.summary_zh

