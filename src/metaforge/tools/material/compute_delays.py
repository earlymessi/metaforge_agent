"""material.compute_delays — 按库存与优先级推算物料就绪延迟。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.utils.material_constraints import compute_material_arrival_delays
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    jobs = params.get("jobs") or ctx.custom_data
    if not jobs:
        return ToolResult(ok=False, error="jobs or context.custom_data required")

    inventory = params.get("inventory") or ctx.extras.get("inventory")
    if not inventory:
        return ToolResult(ok=False, error="inventory required in params or context.extras")

    delays, notes = compute_material_arrival_delays(jobs, inventory)
    data = {
        "arrival_delays": delays,
        "delay_notes": notes,
        "jobs_with_delay": sum(1 for d in delays if d > 0),
    }
    if ctx.artifacts is not None:
        ctx.artifacts["material_delays"] = data
    return ToolResult(ok=True, data=data, artifacts_key="material_delays")


def register_material_compute_delays_tool() -> None:
    name = "material.compute_delays"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="按 BOM 与库存推算各工单物料就绪延迟（小时）",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
