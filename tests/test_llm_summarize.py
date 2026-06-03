"""Summarize 解析测试。"""

from metaforge.orchestrator.llm.parsers import parse_summarize


def test_parse_summarize():
    out = parse_summarize(
        {
            "reasoning_steps": ["完成"],
            "summary_zh": "重排已完成，2个工单拖期。",
            "follow_up": None,
        }
    )
    assert out["summary_zh"] == "重排已完成，2个工单拖期。"
    assert out["planner"] == "llm_summarize"
