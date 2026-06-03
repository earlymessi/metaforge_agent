"""data.propose_persist — 生成 HITL 确认 token。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.services.persist_store import _pick_best_schedule, propose_persist
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    plan_id = params.get("plan_id") or ctx.extras.get("loaded_plan_id") or ctx.plan_id
    if not plan_id:
        loaded = (ctx.artifacts or {}).get("loaded_plan") or {}
        plan_id = loaded.get("plan_id")
    if not plan_id:
        return ToolResult(ok=False, error="plan_id required")

    schedule_results = params.get("schedule_results") or (ctx.artifacts or {}).get("schedule_results")
    if not schedule_results:
        return ToolResult(ok=False, error="schedule_results required")

    solver_id = params.get("solver_id")
    if solver_id and solver_id in schedule_results:
        schedule_result = schedule_results[solver_id]
    else:
        _, schedule_result = _pick_best_schedule(schedule_results)

    delivery_assessment = params.get("delivery_assessment") or (ctx.artifacts or {}).get(
        "delivery_assessment"
    )
    impact_summary = params.get("impact_summary") or (ctx.artifacts or {}).get("impact_summary")
    if not impact_summary:
        impact_report = (ctx.artifacts or {}).get("impact_report")
        if impact_report:
            impact_summary = {
                "summary_zh": impact_report.get("summary_zh") or "",
                "impact_report": impact_report,
            }
    updated_jobs = params.get("jobs") or (ctx.artifacts or {}).get("updated_jobs")
    plan_name = params.get("plan_name") or ctx.extras.get("plan_name") or (ctx.artifacts or {}).get(
        "loaded_plan", {}
    ).get("plan_name")

    from metaforge.services import plan_store
    from metaforge.services.plan_schedule import plan_has_saved_schedule, _previous_schedule_preview

    existing, _ = plan_store.get_plan(str(plan_id))
    has_existing = plan_has_saved_schedule(existing)
    previous_schedule = _previous_schedule_preview(existing) if existing and has_existing else None

    token_data = propose_persist(
        plan_id=str(plan_id),
        schedule_result=schedule_result,
        schedule_results=schedule_results,
        delivery_assessment=delivery_assessment,
        plan_name=plan_name,
        interpretation=(ctx.artifacts or {}).get("interpretation"),
        jobs=updated_jobs,
        impact_summary=impact_summary,
        has_existing_schedule=has_existing,
        previous_schedule=previous_schedule,
    )
    if ctx.artifacts is not None:
        ctx.artifacts["pending_persist"] = token_data
    return ToolResult(ok=True, data=token_data, artifacts_key="pending_persist")


def register_data_propose_persist_tool() -> None:
    name = "data.propose_persist"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="提议将排程结果写入数据库（返回 confirm_token）",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
