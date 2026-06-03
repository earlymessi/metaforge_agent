"""events.reschedule — 统一重排入口。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.services.event_reschedule import dispatch_event_reschedule
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    envelope = params.get("event_envelope") or (ctx.artifacts or {}).get("event_envelope")
    if not envelope:
        return ToolResult(ok=False, error="event_envelope required")

    env = dict(envelope)
    if not env.get("base_jobs") and ctx.custom_data:
        env["base_jobs"] = ctx.custom_data
    opts = dict(env.get("reschedule_options") or {})
    if ctx.extras.get("resource_config"):
        opts["resource_config"] = ctx.extras["resource_config"]
    exec_doc = (ctx.extras or {}).get("production_execution")
    if exec_doc:
        env["production_execution"] = exec_doc
        opts.setdefault("baseline_gantt", exec_doc.get("baseline_gantt"))
        opts.setdefault("baseline_solver", exec_doc.get("baseline_solver"))
        if exec_doc.get("weights"):
            opts.setdefault("weights", exec_doc.get("weights"))
        if exec_doc.get("jobs_snapshot"):
            env["base_jobs"] = exec_doc["jobs_snapshot"]
        sid = exec_doc.get("baseline_solver")
        if sid:
            from metaforge.utils.solver_registry import try_resolve_solver_id

            canon = try_resolve_solver_id(str(sid), default=str(sid).strip())
            opts["baseline_solver"] = canon
            opts["solvers"] = [canon]
    env["reschedule_options"] = opts

    raw = dispatch_event_reschedule(env)
    if raw.get("error"):
        return ToolResult(ok=False, error=raw["error"])

    data = raw.get("data") or {}
    if ctx.artifacts is not None:
        ctx.artifacts["schedule_results"] = data.get("results", {})
        ctx.artifacts["impact_report"] = data.get("impact_report", {})
        if data.get("updated_jobs") is not None:
            ctx.artifacts["updated_jobs"] = data["updated_jobs"]
        ig = data.get("impact_gantt")
        if ig:
            ctx.artifacts["impact_gantt"] = ig
    return ToolResult(
        ok=True,
        data={
            "status": raw.get("status", "success"),
            "results": data.get("results"),
            "impact_report": data.get("impact_report"),
            "updated_jobs": data.get("updated_jobs"),
            "impact_gantt": data.get("impact_gantt"),
            "event_type": env.get("event_type"),
        },
        artifacts_key="schedule_results",
    )


def register_events_reschedule_tool() -> None:
    name = "events.reschedule"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="按事件类型执行重排并返回 impact_report",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
