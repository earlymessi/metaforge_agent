"""material.predict — 排程后物料消耗仿真。"""

from __future__ import annotations

from typing import Any, Dict, List

from metaforge.utils.material_constraints import build_material_report_for_schedule


def _catalog_from_jobs_bom(jobs: Any) -> List[Dict[str, Any]]:
    """从工单 BOM 推导最小物料目录（库存未知时按 0 处理）。"""
    seen: Dict[str, Dict[str, Any]] = {}
    for job in jobs or []:
        bom = job.get("bom") if isinstance(job, dict) else getattr(job, "bom", None)
        if not bom:
            continue
        for line in bom:
            if isinstance(line, dict):
                mid = str(line.get("material_id") or "").strip()
            else:
                mid = str(getattr(line, "material_id", "") or "").strip()
            if not mid or mid in seen:
                continue
            seen[mid] = {
                "id": mid,
                "name": mid,
                "current_stock": 0.0,
                "safe_level": 0.0,
                "unit": "pcs",
            }
    return list(seen.values())
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    gantt: List[Dict[str, Any]] = list(
        params.get("schedule_data")
        or params.get("gantt_data")
        or []
    )
    if not gantt:
        sr = (ctx.artifacts or {}).get("schedule_results") or {}
        if sr:
            best = params.get("solver_id")
            if best and best in sr:
                gantt = sr[best].get("gantt_data") or []
            else:
                first = next(iter(sr.values()), {})
                gantt = first.get("gantt_data") or []

    jobs = params.get("jobs") or ctx.custom_data
    catalog = params.get("material_catalog") or ctx.extras.get("material_catalog")
    if not catalog and jobs:
        catalog = _catalog_from_jobs_bom(jobs)
    if not gantt or not jobs:
        return ToolResult(ok=False, error="need gantt and jobs")
    if not catalog:
        return ToolResult(
            ok=False,
            error="need material_catalog (物料主数据为空，请在「加工物料调度」补货或检查 MongoDB materials_inventory)",
        )

    report = build_material_report_for_schedule(gantt, jobs, catalog)
    if ctx.artifacts is not None:
        ctx.artifacts["material_report"] = report
    return ToolResult(ok=True, data=report, artifacts_key="material_report")


def register_material_predict_tool() -> None:
    name = "material.predict"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="基于甘特与 BOM 预测物料消耗与风险",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
