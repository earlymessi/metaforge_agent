"""Orchestrator preview / execution_trace 测试。"""

import os

from metaforge.orchestrator.execution_trace import build_route_trace
from metaforge.orchestrator.preview import build_orchestrator_preview


def test_build_route_trace_rule():
    trace = build_route_trace(
        {
            "agent_id": "events",
            "router": "rule",
            "rule_reason_zh": "匹配关键词：故障",
        }
    )
    assert trace["phase"] == "route"
    assert "故障" in "\n".join(trace["lines"])


def test_orchestrator_preview_scheduling():
    os.environ["LLM_ENABLED"] = "0"
    out = build_orchestrator_preview("用 SPT 排程", intent="schedule")
    assert out["status"] == "preview"
    assert out["agent_id"] == "scheduling"
    assert len(out["trace"]) >= 2
    phases = [t["phase"] for t in out["trace"]]
    assert "route" in phases
    assert "plan" in phases


def test_resolve_plan_phase_natural_language_no_nameerror():
    """纯中文、无显式 intent 时不应因未定义变量崩溃。"""
    from metaforge.orchestrator.preview import resolve_plan_phase
    from metaforge.orchestrator.router import coerce_route_for_message

    os.environ["LLM_ENABLED"] = "0"
    route = coerce_route_for_message("用 SPT 排程", None, context={})
    agent, areq, steps, _planner, _block = resolve_plan_phase(
        route, "用 SPT 排程", context={}
    )
    assert route.get("agent_id") == "scheduling"
    assert agent.agent_id == "scheduling"
    assert len(steps) >= 1
