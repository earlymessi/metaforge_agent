"""排程意图解析 v2：澄清、动态 plan、confidence。"""

import os

import pytest

from metaforge.scheduling.context import ContextManager
from metaforge.scheduling.intent_types import ScheduleIntentType
from metaforge.scheduling.resolve_intent import resolve_schedule_intent


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
