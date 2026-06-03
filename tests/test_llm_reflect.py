"""Reflection 解析测试。"""

import pytest

from metaforge.orchestrator.llm.parsers import parse_reflect


def test_parse_reflect_retry():
    out = parse_reflect(
        {
            "action": "retry",
            "tool": "scheduling.run",
            "params": {"solvers": ["spt"]},
            "feedback_zh": "改用 spt 单算法",
            "is_valid": False,
        },
        allowed_tools=["scheduling.run", "scheduling.parse_intent"],
    )
    assert out["action"] == "retry"
    assert out["tool"] == "scheduling.run"


def test_parse_reflect_clarify():
    out = parse_reflect(
        {"action": "clarify", "message_zh": "请说明优化目标"},
        allowed_tools=["scheduling.run"],
    )
    assert out["action"] == "clarify"
    assert "目标" in out["message_zh"]


def test_parse_reflect_human():
    out = parse_reflect(
        {"action": "human", "message_zh": "影响工单过多，需主管确认"},
        allowed_tools=["events.reschedule"],
    )
    assert out["action"] == "human"


def test_parse_reflect_rejects_unknown_retry_tool():
    with pytest.raises(ValueError, match="not allowed"):
        parse_reflect(
            {"action": "retry", "tool": "data.delete_plan", "params": {}},
            allowed_tools=["scheduling.run"],
        )
