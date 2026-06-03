"""ReAct 决策解析测试。"""

import pytest

from metaforge.orchestrator.llm.parsers import parse_react_decision


def test_parse_react_finish():
    out = parse_react_decision(
        {"action": "finish", "answer": "排程已完成"},
        allowed_tools=["scheduling.run"],
    )
    assert out["action"] == "finish"
    assert out["answer"] == "排程已完成"


def test_parse_react_call_tool():
    out = parse_react_decision(
        {"action": "call_tool", "tool": "scheduling.run", "params": {}},
        allowed_tools=["scheduling.run", "scheduling.parse_intent"],
    )
    assert out["action"] == "call_tool"
    assert out["tool"] == "scheduling.run"


def test_parse_react_rejects_unknown_tool():
    with pytest.raises(ValueError, match="not allowed"):
        parse_react_decision(
            {"action": "call_tool", "tool": "data.delete_plan", "params": {}},
            allowed_tools=["scheduling.run"],
        )
