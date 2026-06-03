"""Orchestrator 预览：路由 + 计划 + 解析（不执行 Tool）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from metaforge.agents.base import AgentRequest, PlanStep
from metaforge.orchestrator.execution_trace import build_plan_trace, build_route_trace
from metaforge.orchestrator.router import get_agent, resolve_agent_route

AGENT_TO_INTENT = {
    "scheduling": "schedule",
    "events": "reschedule",
    "kitting": "kitting",
    "commitment": "commitment",
    "whatif": "whatif",
    "plans": "plans",
}


def cache_plan_on_request(areq: AgentRequest, steps: List[PlanStep], plan_planner: str) -> None:
    """预览阶段已生成 Plan 时写入 context，避免 run() 再次调用 GLM Plan。"""
    areq.context.setdefault("extras", {})
    areq.context["extras"]["cached_plan_steps"] = [s.to_dict() for s in steps]
    areq.context["extras"]["cached_plan_planner"] = plan_planner


def resolve_route_phase(
    message: str = "",
    intent: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from metaforge.orchestrator.router import coerce_route_for_message

    return coerce_route_for_message(message, intent, context=context)


def resolve_plan_phase(
    route: Dict[str, Any],
    message: str,
    *,
    context: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, AgentRequest, List[PlanStep], str, Dict[str, Any]]:
    agent_id = route["agent_id"]
    agent = get_agent(agent_id)
    areq = AgentRequest(
        message=message,
        params=dict(params or {}),
        context=dict(context or {}),
    )
    route_intent = route.get("intent")
    if route.get("router") == "explicit" or route_intent in (
        "schedule",
        "pipeline",
    ):
        areq.params.setdefault("_skip_vague_clarify", True)
    steps = agent.build_plan(areq)
    plan_planner = getattr(agent, "_plan_planner", "rule")
    block = build_plan_trace(agent_id, steps, plan_planner=plan_planner)
    cache_plan_on_request(areq, steps, plan_planner)
    return agent, areq, steps, plan_planner, block


def resolve_parse_phase(
    agent_id: str,
    message: str,
    areq: AgentRequest,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    msg = (message or "").strip()
    if not msg:
        return None
    parse_data: Optional[Dict[str, Any]] = None
    if agent_id == "scheduling":
        from metaforge.scheduling.resolve_intent import resolve_schedule_intent

        parse_data = resolve_schedule_intent({"message": msg})
    elif agent_id == "events":
        from metaforge.orchestrator.router import has_pending_insert_job_intake

        if has_pending_insert_job_intake(areq.context):
            intake = (areq.context.get("artifacts") or {}).get("insert_job_intake") or {}
            draft = intake.get("draft") or {}
            parse_data = {
                "event_type": "insert_order",
                "summary_zh": "会话续聊：合并用户补充的工艺（不重新 parse 整句）",
                "params": {
                    "insert_job": draft,
                    "mode": (intake.get("params_snapshot") or {}).get("mode", "local_repair"),
                },
                "planner": "session_continue",
            }
        else:
            from metaforge.events.resolve_event import resolve_event_envelope

            base = areq.context.get("custom_data")
            parse_data = resolve_event_envelope(msg, base_jobs=base, params=params)

    if not parse_data:
        return None
    from metaforge.orchestrator.execution_trace import build_parse_trace

    return build_parse_trace(agent_id, parse_data)


def iter_preview_trace_blocks(
    message: str = "",
    intent: Optional[str] = None,
    *,
    context: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
):
    """按阶段产出 trace 块（路由 → 计划 → 解析），供流式推送。"""
    route = resolve_route_phase(message, intent, context=context)
    yield build_route_trace(route)

    agent, areq, steps, plan_planner, plan_block = resolve_plan_phase(
        route, message, context=context, params=params
    )
    yield plan_block

    parse_block = resolve_parse_phase(route["agent_id"], message, areq, params)
    if parse_block:
        yield parse_block

    return route, agent, areq, steps, plan_planner, parse_block


def build_orchestrator_preview(
    message: str = "",
    intent: Optional[str] = None,
    *,
    context: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    gen = iter_preview_trace_blocks(message, intent, context=context, params=params)
    trace = []
    route = agent_id = plan_planner = None
    try:
        while True:
            trace.append(next(gen))
    except StopIteration as stop:
        route, agent, areq, steps, plan_planner, _parse = stop.value
    agent_id = route["agent_id"]
    return {
        "status": "preview",
        "agent_id": agent_id,
        "route": route,
        "router_planner": route.get("router"),
        "router_intent": route.get("intent"),
        "router_reason_zh": route.get("reason_zh") or route.get("rule_reason_zh"),
        "plan_planner": plan_planner,
        "trace": trace,
    }
