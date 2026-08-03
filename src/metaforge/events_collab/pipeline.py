from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from metaforge.events_collab.trace import build_events_trace
from metaforge.tools.base import ToolContext, ToolResult

# Keep in sync with legacy EventsAgentRunner catalog detection.
_CATALOG_QUERY_RE = re.compile(
    r"支持哪些|有哪些事件|事件类型|能处理什么异常",
    re.I,
)

InvokeTool = Callable[[str, Dict[str, Any], ToolContext], ToolResult]


def _default_invoke(name: str, params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    from metaforge.tools.load_all import load_all_tools
    from metaforge.tools.registry import run_tool

    load_all_tools()
    return run_tool(name, params or {}, ctx)


def _merge_tool_data(ctx: ToolContext, result: ToolResult) -> None:
    if not result.ok or result.data is None:
        return
    key = result.artifacts_key
    if not key:
        if isinstance(result.data, dict):
            ctx.artifacts.update(result.data)
        return
    if key == "schedule_results" and isinstance(result.data, dict):
        rd = result.data
        if isinstance(rd.get("results"), dict):
            ctx.artifacts["schedule_results"] = rd["results"]
        for k in ("impact_report", "impact_gantt", "updated_jobs", "event_type"):
            if rd.get(k) is not None:
                ctx.artifacts[k] = rd[k]
        return
    # Overwrite: intake/envelope tools refresh the same keys across steps.
    ctx.artifacts[key] = result.data


def _tool_context_from(context: Optional[dict], params: Optional[dict]) -> ToolContext:
    ctx = dict(context or {})
    params = dict(params or {})
    return ToolContext(
        custom_data=ctx.get("custom_data"),
        benchmark_file=ctx.get("benchmark_file"),
        plan_id=ctx.get("plan_id"),
        weights=ctx.get("weights") or params.get("weights"),
        enforce_material=bool(ctx.get("enforce_material", False)),
        random_seed=ctx.get("random_seed"),
        artifacts=dict(ctx.get("artifacts") or {}),
        extras=dict(ctx.get("extras") or {}),
    )


def _envelope(params: dict) -> Optional[dict]:
    env = params.get("event_envelope")
    if isinstance(env, dict) and env.get("event_type"):
        return env
    return None


def _insert_pending(context: dict) -> bool:
    from metaforge.orchestrator.router import has_pending_insert_job_intake

    return has_pending_insert_job_intake(context)


def _call(
    invoke: InvokeTool,
    tool: str,
    params: Dict[str, Any],
    ctx: ToolContext,
    *,
    optional: bool = False,
) -> tuple[ToolResult, Dict[str, Any]]:
    result = invoke(tool, params, ctx)
    entry = {"tool": tool, "ok": bool(result.ok), "optional": optional}
    if result.ok:
        _merge_tool_data(ctx, result)
    else:
        entry["error"] = result.error
    return result, entry


def run_events(
    *,
    message: str = "",
    context: dict | None = None,
    params: dict | None = None,
    invoke_tool: InvokeTool | None = None,
) -> dict:
    """
    Fixed-stage events orchestration.

    Returns dict with status/summary_zh/artifacts/pending_action/plan;
    artifacts always include events_trace.
    """
    context = dict(context or {})
    params = dict(params or {})
    invoke = invoke_tool or _default_invoke
    tool_ctx = _tool_context_from(context, params)
    if message and "message" not in tool_ctx.extras:
        tool_ctx.extras["message"] = message

    stages: List[str] = []
    tool_log: List[Dict[str, Any]] = []
    plan: List[Dict[str, Any]] = []
    warnings: List[str] = []
    envelope = _envelope(params)

    def finish(status: str, summary_zh: str, **extra) -> dict:
        event_type = (
            (tool_ctx.artifacts.get("event_type"))
            or (envelope or {}).get("event_type")
            or (tool_ctx.artifacts.get("event_envelope") or {}).get("event_type")
        )
        impact = tool_ctx.artifacts.get("impact_report") or (
            (tool_ctx.artifacts.get("impact_summary") or {}).get("impact_report")
        )
        if impact and "impact_report" not in tool_ctx.artifacts:
            tool_ctx.artifacts["impact_report"] = impact
        trace = build_events_trace(
            status=status,
            stages=stages,
            event_type=event_type,
            tool_log=tool_log,
            warnings=warnings,
        )
        tool_ctx.artifacts["events_trace"] = trace
        out = {
            "status": status,
            "summary_zh": summary_zh,
            "artifacts": dict(tool_ctx.artifacts),
            "plan": plan,
            "events_trace": trace,
        }
        out.update(extra)
        return out

    # --- catalog short path ---
    msg = (message or "").strip()
    if msg and _CATALOG_QUERY_RE.search(msg):
        stages.append("catalog")
        result, entry = _call(invoke, "events.list_event_types", {}, tool_ctx)
        tool_log.append(entry)
        plan.append({"step_id": "s0", "tool": "events.list_event_types", "status": "completed" if result.ok else "failed"})
        if not result.ok:
            return finish("failed", result.error or "列出事件类型失败", error=result.error)
        catalog = tool_ctx.artifacts.get("event_type_catalog") or {}
        names = [e.get("name_zh") for e in (catalog.get("event_types") or [])[:6]]
        summary = "支持的事件类型：" + "、".join(n for n in names if n) + " 等。" if names else "已返回事件类型目录。"
        return finish("success", summary)

    # --- insert intake pending ---
    if _insert_pending(context):
        stages.append("intake")
        for step_id, tool, p in (
            ("m1", "events.merge_insert_job", {"message": message}),
            ("m2", "events.check_insert_job", {"message": message}),
        ):
            result, entry = _call(invoke, tool, p, tool_ctx)
            tool_log.append(entry)
            plan.append(
                {
                    "step_id": step_id,
                    "tool": tool,
                    "status": "completed" if result.ok else "failed",
                }
            )
            if not result.ok:
                return finish("failed", result.error or f"{tool} 失败", error=result.error)
            intake = tool_ctx.artifacts.get("insert_job_intake") or {}
            if tool == "events.check_insert_job" and intake.get("status") == "need_input":
                from metaforge.memory.manager import MemoryManager

                mm = MemoryManager.from_context(context)
                mm.set_working("events", "insert_job_intake", intake)
                return finish(
                    "need_input",
                    intake.get("question_zh") or "请补充插单工序信息。",
                    pending_action={
                        "type": "insert_job_details",
                        "missing_fields": intake.get("missing_fields") or [],
                        "draft": intake.get("draft"),
                    },
                )
        # continue to reschedule after successful intake
        stages.append("reschedule")
        reschedule_params: Dict[str, Any] = {}
        if envelope:
            reschedule_params["event_envelope"] = envelope
        result, entry = _call(invoke, "events.reschedule", reschedule_params, tool_ctx)
        tool_log.append(entry)
        plan.append(
            {
                "step_id": "s2",
                "tool": "events.reschedule",
                "status": "completed" if result.ok else "failed",
            }
        )
        if not result.ok:
            return finish("failed", result.error or "重排失败", error=result.error)
        stages.append("explain")
        result, entry = _call(invoke, "delivery.explain_impact", {}, tool_ctx)
        tool_log.append(entry)
        plan.append(
            {
                "step_id": "s3",
                "tool": "delivery.explain_impact",
                "status": "completed" if result.ok else "failed",
            }
        )
        if not result.ok:
            return finish("failed", result.error or "影响说明失败", error=result.error)
        summary = (tool_ctx.artifacts.get("impact_summary") or {}).get("summary_zh") or "插单重排完成。"
        return finish("success", summary)

    # --- default reschedule chain ---
    stages.append("get_state")
    result, entry = _call(invoke, "execution.get_state", {}, tool_ctx, optional=True)
    tool_log.append(entry)
    plan.append(
        {
            "step_id": "s0",
            "tool": "execution.get_state",
            "status": "completed" if result.ok else "skipped",
        }
    )

    if not params.get("skip_parse"):
        stages.append("parse")
        parse_params = {"message": message, "event_envelope": envelope}
        result, entry = _call(invoke, "events.parse_event", parse_params, tool_ctx)
        tool_log.append(entry)
        plan.append(
            {
                "step_id": "s1",
                "tool": "events.parse_event",
                "status": "completed" if result.ok else "failed",
            }
        )
        if not result.ok:
            return finish("failed", result.error or "事件解析失败", error=result.error)

    stages.append("check_insert")
    result, entry = _call(invoke, "events.check_insert_job", {"message": message}, tool_ctx)
    tool_log.append(entry)
    plan.append(
        {
            "step_id": "s1b",
            "tool": "events.check_insert_job",
            "status": "completed" if result.ok else "failed",
        }
    )
    if not result.ok:
        return finish("failed", result.error or "插单检查失败", error=result.error)
    intake = tool_ctx.artifacts.get("insert_job_intake") or {}
    if intake.get("status") == "need_input":
        from metaforge.memory.manager import MemoryManager

        mm = MemoryManager.from_context(context)
        mm.set_working("events", "insert_job_intake", intake)
        return finish(
            "need_input",
            intake.get("question_zh") or "请补充插单工序信息。",
            pending_action={
                "type": "insert_job_details",
                "missing_fields": intake.get("missing_fields") or [],
                "draft": intake.get("draft"),
            },
        )

    stages.append("reschedule")
    reschedule_params = {}
    if envelope:
        reschedule_params["event_envelope"] = envelope
    # prefer envelope from parse artifacts
    parsed_env = tool_ctx.artifacts.get("event_envelope")
    if isinstance(parsed_env, dict) and parsed_env.get("event_type") and "event_envelope" not in reschedule_params:
        reschedule_params["event_envelope"] = parsed_env
    result, entry = _call(invoke, "events.reschedule", reschedule_params, tool_ctx)
    tool_log.append(entry)
    plan.append(
        {
            "step_id": "s2",
            "tool": "events.reschedule",
            "status": "completed" if result.ok else "failed",
        }
    )
    if not result.ok:
        return finish("failed", result.error or "重排失败", error=result.error)

    stages.append("compare")
    result, entry = _call(invoke, "delivery.compare_commitment", {}, tool_ctx, optional=True)
    tool_log.append(entry)
    plan.append(
        {
            "step_id": "s3",
            "tool": "delivery.compare_commitment",
            "status": "completed" if result.ok else "skipped",
        }
    )

    stages.append("explain")
    result, entry = _call(invoke, "delivery.explain_impact", {}, tool_ctx)
    tool_log.append(entry)
    plan.append(
        {
            "step_id": "s4",
            "tool": "delivery.explain_impact",
            "status": "completed" if result.ok else "failed",
        }
    )
    if not result.ok:
        return finish("failed", result.error or "影响说明失败", error=result.error)

    summary = (tool_ctx.artifacts.get("impact_summary") or {}).get("summary_zh") or "异常重排完成。"
    out = finish("success", summary)
    impact = out["artifacts"].get("impact_report")
    if impact:
        out["ui_action"] = {
            "type": "navigate",
            "path": "/",
            "hint": "可在生产看板查看双甘特对比与实时执行甘特",
        }
    return out
