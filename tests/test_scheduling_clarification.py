"""模糊/不可映射目标的澄清阻塞测试。"""

import os

import pytest

from metaforge.scheduling.intent_types import ScheduleIntentType
from metaforge.scheduling.resolve_intent import resolve_schedule_intent


@pytest.fixture(autouse=True)
def _env():
    os.environ.pop("LLM_ENABLED", None)
    os.environ["LLM_ENABLED"] = "0"
    yield


def test_shortest_time_schedule_does_not_clarify():
    result = resolve_schedule_intent(
        {"message": "最短时间排程"},
        session_id="short-time",
    )
    assert result["intent_type"] != "CLARIFICATION"
    assert result.get("full_compare")
    assert result["schedule_goal"] == "makespan"


def test_satisfaction_goal_requires_clarification():
    result = resolve_schedule_intent(
        {"message": "帮我进行让用户满意度最高的排程"},
        session_id="sat-1",
    )
    assert result["intent_type"] == ScheduleIntentType.CLARIFICATION.value
    assert result.get("parse_note_zh")
    assert "满意度" in (result.get("parse_note_zh") or "")
    assert result["solvers"] == []
    assert result.get("needs_user_reply") is True


def test_clarification_reply_option_one_continues_schedule():
    from metaforge.scheduling.context import ContextManager

    resolve_schedule_intent(
        {"message": "帮我进行让用户满意度最高的排程"},
        session_id="sat-opt1",
    )
    assert ContextManager.get_pending("sat-opt1") is not None

    result = resolve_schedule_intent({"message": "①"}, session_id="sat-opt1")
    assert result["intent_type"] != "CLARIFICATION"
    assert result.get("full_compare")
    assert result["schedule_goal"] == "weighted_tardiness_total"
    assert result["strategy_id"] == "delivery"
    assert len(result["solvers"]) >= 8
    assert "满意度" not in (result.get("parse_note_zh") or "")
    assert ContextManager.get_pending("sat-opt1") is None
