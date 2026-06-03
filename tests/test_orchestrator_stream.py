"""Orchestrator 流式 trace 工具测试。"""

from metaforge.orchestrator.execution_trace import format_plan_log_line
from metaforge.orchestrator.stream import sse_event


def test_format_plan_log_line():
    line = format_plan_log_line(
        {"step_id": "s1", "tool": "scheduling.run", "status": "completed", "duration_ms": 12.5}
    )
    assert "s1" in line
    assert "completed" in line
    assert "12.5" in line


def test_sse_event_json():
    raw = sse_event({"event": "trace_block", "block": {"phase": "route"}})
    assert raw.startswith("data: ")
    assert "trace_block" in raw
