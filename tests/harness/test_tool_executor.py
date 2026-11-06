"""ToolExecutor risk / schema / timeout / retry."""

from __future__ import annotations

import time

import pytest

from metaforge.harness.tool_executor import execute_tool, execute_tool_with_events
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import _TOOL_REGISTRY, register_tool


@pytest.fixture
def _clean_demo_tools():
    names = [
        "demo.allow",
        "demo.ask",
        "demo.deny",
        "demo.slow",
        "demo.flaky",
        "demo.required",
    ]
    for n in names:
        _TOOL_REGISTRY.pop(n, None)
    yield
    for n in names:
        _TOOL_REGISTRY.pop(n, None)


def _reg(spec: ToolSpec) -> None:
    _TOOL_REGISTRY.pop(spec.name, None)
    register_tool(spec)


def test_allow_runs(_clean_demo_tools):
    _reg(
        ToolSpec(
            name="demo.allow",
            description_zh="ok",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=lambda p, c: ToolResult(ok=True, data={"v": p.get("x", 1)}),
            risk_level="allow",
        )
    )
    result, events = execute_tool_with_events("demo.allow", {"x": 2}, ToolContext())
    assert result.ok
    assert result.data["v"] == 2
    assert any(e["type"] == "tool.start" for e in events)
    assert any(e["type"] == "tool.end" for e in events)


def test_deny_blocked(_clean_demo_tools):
    _reg(
        ToolSpec(
            name="demo.deny",
            description_zh="no",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=lambda p, c: ToolResult(ok=True, data={}),
            risk_level="deny",
        )
    )
    result = execute_tool("demo.deny", {}, ToolContext())
    assert not result.ok
    assert "denied" in (result.error or "")


def test_ask_needs_hitl_without_approval(_clean_demo_tools):
    called = {"n": 0}

    def handler(p, c):
        called["n"] += 1
        return ToolResult(ok=True, data={})

    _reg(
        ToolSpec(
            name="demo.ask",
            description_zh="ask",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=handler,
            risk_level="ask",
        )
    )
    result = execute_tool("demo.ask", {}, ToolContext())
    assert not result.ok
    assert result.data.get("needs_hitl") is True
    assert called["n"] == 0


def test_ask_runs_with_tool_approved(_clean_demo_tools):
    _reg(
        ToolSpec(
            name="demo.ask",
            description_zh="ask",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=lambda p, c: ToolResult(ok=True, data={"ok": True}),
            risk_level="ask",
        )
    )
    ctx = ToolContext(extras={"tool_approved": True})
    result = execute_tool("demo.ask", {}, ctx)
    assert result.ok


def test_ask_runs_with_skip_strategy_hitl(_clean_demo_tools):
    _reg(
        ToolSpec(
            name="demo.ask",
            description_zh="ask",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=lambda p, c: ToolResult(ok=True, data={"ok": True}),
            risk_level="ask",
        )
    )
    result = execute_tool("demo.ask", {"skip_strategy_hitl": True}, ToolContext())
    assert result.ok


def test_required_input_validation(_clean_demo_tools):
    _reg(
        ToolSpec(
            name="demo.required",
            description_zh="req",
            input_schema={
                "type": "object",
                "required": ["user_goal"],
                "properties": {"user_goal": {"type": "string"}},
            },
            output_schema={"type": "object"},
            handler=lambda p, c: ToolResult(ok=True, data=p),
            risk_level="allow",
        )
    )
    result = execute_tool("demo.required", {}, ToolContext())
    assert not result.ok
    assert "user_goal" in (result.error or "")


def test_timeout(_clean_demo_tools):
    def slow(p, c):
        time.sleep(0.5)
        return ToolResult(ok=True, data={})

    _reg(
        ToolSpec(
            name="demo.slow",
            description_zh="slow",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=slow,
            risk_level="allow",
            timeout_seconds=0.05,
        )
    )
    result = execute_tool("demo.slow", {}, ToolContext())
    assert not result.ok
    assert result.data.get("timeout") is True


def test_retry_on_error(_clean_demo_tools):
    state = {"n": 0}

    def flaky(p, c):
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("boom")
        return ToolResult(ok=True, data={"n": state["n"]})

    _reg(
        ToolSpec(
            name="demo.flaky",
            description_zh="flaky",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=flaky,
            risk_level="allow",
            retry_policy={"max_retries": 3},
        )
    )
    result, events = execute_tool_with_events("demo.flaky", {}, ToolContext())
    assert result.ok
    assert state["n"] == 3
    assert any(e["type"] == "tool.retry" for e in events)
