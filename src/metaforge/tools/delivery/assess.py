"""delivery.assess — 交期承诺评估。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from metaforge.utils.delivery_prediction import compute_delivery_predictions
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool

_VERDICT = {
    "on_time": "可满足",
    "low": "可满足",
    "medium": "勉强可满足，需跟踪",
    "high": "当前计划无法满足",
    "critical": "当前计划无法满足",
    "unknown": "无法承诺（未设交期）",
}


def _overall_from_jobs(jobs: List[Dict[str, Any]]) -> str:
    levels = {j.get("risk_level") for j in jobs}
    if levels <= {"on_time", "low"}:
        return "met"
    if "critical" in levels or "high" in levels:
        return "not_met"
    if "medium" in levels:
        return "partial"
    return "unknown"


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    gantt: List[Dict[str, Any]] = list(params.get("gantt_data") or [])
    problem = params.get("problem") or ctx.extras.get("problem")
    job_name_map = params.get("job_name_map") or {}

    if not gantt:
        sr = (ctx.artifacts or {}).get("schedule_results") or {}
        if sr:
            sid = params.get("solver_id")
            entry = sr.get(sid) if sid else next(iter(sr.values()), {})
            gantt = entry.get("gantt_data") or []
            cv = (entry.get("metrics") or {}).get("machine_busy_cv")
        else:
            cv = None
    else:
        cv = params.get("machine_busy_cv")

    if problem is None and ctx.custom_data:
        from metaforge.utils.problem_builder import build_problem_from_custom_jobs

        problem, built_map, _ = build_problem_from_custom_jobs(
            ctx.custom_data, instance_name="Delivery Assess"
        )
        if not job_name_map:
            job_name_map = built_map

    if not gantt or problem is None:
        return ToolResult(ok=False, error="gantt_data and problem required")

    preds = compute_delivery_predictions(
        gantt,
        problem,
        job_name_map=job_name_map,
        machine_busy_cv=cv,
    )
    jobs_out = []
    for p in preds:
        rl = p.get("risk_level", "unknown")
        jobs_out.append({**p, "verdict_zh": _VERDICT.get(rl, rl)})

    overall = _overall_from_jobs(jobs_out)
    high = sum(1 for j in jobs_out if j.get("risk_level") in ("high", "critical"))
    low = sum(1 for j in jobs_out if j.get("risk_level") in ("on_time", "low"))
    summary = f"共 {len(jobs_out)} 单：可满足 {low} 单，高风险 {high} 单。"
    if overall == "not_met":
        summary += " 整体结论：当前计划难以满足客户交期。"

    assessment = {
        "overall": overall,
        "counts": {
            "total": len(jobs_out),
            "on_time": low,
            "high_risk": high,
        },
        "jobs": jobs_out,
        "summary_zh": summary,
    }
    if ctx.artifacts is not None:
        ctx.artifacts["delivery_assessment"] = assessment
        ctx.artifacts["delivery_predictions"] = jobs_out
    return ToolResult(ok=True, data=assessment, artifacts_key="delivery_assessment")


def register_delivery_assess_tool() -> None:
    name = "delivery.assess"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="评估排程结果是否满足工单交期",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
