"""Orchestrator SSE：思考过程按阶段 / 按步骤实时推送。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional

from metaforge.agents.base import AgentRequest, AgentResponse
from metaforge.orchestrator.execution_trace import (
    build_execution_trace_shell,
    build_route_trace,
    format_plan_log_line,
    merge_run_trace,
)
from metaforge.orchestrator.preview import (
    resolve_parse_phase,
    resolve_plan_phase,
    resolve_route_phase,
)
from metaforge.utils.bson_safe import to_bson_safe


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict") and callable(obj.dict):
        return obj.dict()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def sse_event(payload: Dict[str, Any]) -> str:
    safe = to_bson_safe(payload)
    return f"data: {json.dumps(safe, ensure_ascii=False, default=_json_default)}\n\n"


async def iter_orchestrator_sse(
    message: str,
    intent: Optional[str],
    ctx: Dict[str, Any],
    params: Dict[str, Any],
    *,
    prepare_areq=None,
    run_agent_fn,
    finalize_out=None,
) -> AsyncIterator[str]:
    preview_trace: List[Dict[str, Any]] = []
    plan_planner = "rule"

    yield sse_event({"event": "status", "text": "正在识别意图路由…"})
    route = await asyncio.to_thread(resolve_route_phase, message, intent, ctx)
    from metaforge.orchestrator.router import coerce_route_for_message

    route = await asyncio.to_thread(coerce_route_for_message, message, intent, route, ctx)
    route_block = build_route_trace(route)
    preview_trace.append(route_block)
    yield sse_event({"event": "trace_block", "block": route_block})

    if route.get("out_of_scope"):
        from metaforge.orchestrator.execution_trace import build_scope_guidance_trace

        scope_block = build_scope_guidance_trace(route)
        preview_trace.append(scope_block)
        yield sse_event({"event": "trace_block", "block": scope_block})
        out = {
            "status": "out_of_scope",
            "agent_id": None,
            "summary_zh": route.get("guidance_zh") or "",
            "scope_category": route.get("scope_category"),
            "execution_trace": preview_trace,
            "router_planner": route.get("router"),
            "router_intent": route.get("intent"),
            "router_reason_zh": route.get("reason_zh"),
        }
        yield sse_event({"event": "done", "data": to_bson_safe(out)})
        return

    yield sse_event({"event": "status", "text": "正在生成执行计划…"})
    agent, areq, _steps, plan_planner, plan_block = await asyncio.to_thread(
        resolve_plan_phase,
        route,
        message,
        context=ctx,
        params=params,
    )
    preview_trace.append(plan_block)
    yield sse_event({"event": "trace_block", "block": plan_block})

    agent_id = route["agent_id"]
    msg = (message or "").strip()
    insert_followup = False
    if agent_id == "events":
        from metaforge.orchestrator.router import has_pending_insert_job_intake

        insert_followup = has_pending_insert_job_intake(ctx)
    if msg and agent_id in ("scheduling", "events"):
        if insert_followup:
            parse_status = "正在合并插单工艺补充…"
        elif agent_id == "scheduling":
            parse_status = "正在解析排程/异常参数…"
        else:
            parse_status = "正在解析异常事件…"
        yield sse_event({"event": "status", "text": parse_status})
        parse_block = await asyncio.to_thread(
            resolve_parse_phase, agent_id, message, areq, params
        )
        if parse_block:
            preview_trace.append(parse_block)
            yield sse_event({"event": "trace_block", "block": parse_block})

    if prepare_areq is not None:
        areq = await prepare_areq(route, agent, areq, preview_trace)

    yield sse_event({"event": "status", "text": "正在执行 Tool 链…"})
    yield sse_event({"event": "trace_block", "block": build_execution_trace_shell()})

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _emit(ev: Dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    def _run() -> AgentResponse | Dict[str, Any]:
        def on_step_start(entry: Dict[str, Any]) -> None:
            _emit(
                {
                    "event": "trace_execute_line",
                    "line": f"{entry.get('step_id', '?')} {entry.get('tool', '?')} → 执行中…",
                    "running": True,
                }
            )

        def on_step_done(entry: Dict[str, Any]) -> None:
            _emit(
                {
                    "event": "trace_execute_line",
                    "line": format_plan_log_line(entry),
                    "replace_running": True,
                }
            )

        return run_agent_fn(
            agent,
            areq,
            preview_trace,
            route,
            on_step_start=on_step_start,
            on_step_done=on_step_done,
        )

    task = asyncio.create_task(asyncio.to_thread(_run))
    while not task.done() or not queue.empty():
        try:
            ev = await asyncio.wait_for(queue.get(), timeout=0.05)
            yield sse_event(ev)
        except asyncio.TimeoutError:
            continue

    result = await task
    if isinstance(result, dict):
        out = result
    else:
        out = result.to_dict()
        out["agent_id"] = agent_id
        out["execution_trace"] = merge_run_trace(preview_trace, out.get("plan") or [])
        out["router_planner"] = route.get("router")
        if route.get("intent"):
            out["router_intent"] = route["intent"]
        if route.get("llm_error"):
            out["router_llm_error"] = route["llm_error"]
        # Prefer agent response planner (e.g. events_collab) over preview cache.
        out["plan_planner"] = out.get("plan_planner") or plan_planner
        reason = route.get("reason_zh") or route.get("rule_reason_zh")
        if reason:
            out["router_reason_zh"] = reason

    if finalize_out is not None:
        out = await finalize_out(out, route, preview_trace, agent_id, areq)

    yield sse_event({"event": "done", "data": to_bson_safe(out)})
