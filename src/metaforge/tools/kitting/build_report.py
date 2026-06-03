"""kitting.build_report — 齐套报告聚合。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    static = params.get("material_check") or (ctx.artifacts or {}).get("material_check")
    if not static:
        return ToolResult(ok=False, error="material_check required")

    blocking = []
    for pj in static.get("per_job", []):
        if not pj.get("feasible", True):
            shortages = [ln for ln in pj.get("lines", []) if not ln.get("feasible", True)]
            blocking.append(
                {
                    "job_name": pj.get("job_name"),
                    "shortages": shortages,
                }
            )

    can_start_all = static.get("feasible", False) and not blocking
    rec_parts = []
    if can_start_all:
        rec_parts.append("静态齐套检查通过，可以安排开工。")
    else:
        rec_parts.append("存在缺料，不建议按计划同时开工。")
        for b in blocking[:3]:
            rec_parts.append(f"{b['job_name']} 缺料。")

    delays = (ctx.artifacts or {}).get("material_delays") or {}
    delay_notes = delays.get("delay_notes") or []
    if delay_notes:
        rec_parts.append(f"有 {len(delay_notes)} 个工单因库存不足需延后开工。")

    predict = (ctx.artifacts or {}).get("material_report")
    if predict:
        rec_parts.append("已根据排程结果完成物料消耗仿真，请关注仿真报告中的击穿风险。")

    report = {
        "can_start_all": can_start_all,
        "static_check": static,
        "blocking_jobs": blocking,
        "material_predict": predict,
        "recommendation_zh": "".join(rec_parts),
    }
    if ctx.artifacts is not None:
        ctx.artifacts["kitting_report"] = report
    return ToolResult(ok=True, data=report, artifacts_key="kitting_report")


def register_kitting_build_report_tool() -> None:
    name = "kitting.build_report"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="聚合静态齐套与排程后物料仿真为 kitting_report",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
