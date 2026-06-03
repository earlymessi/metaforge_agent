"""material.check_static — 静态齐套检查。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.utils.material_constraints import check_jobs_material_static
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    jobs = params.get("jobs") or ctx.custom_data
    if not jobs:
        return ToolResult(ok=False, error="jobs or context.custom_data required")

    inventory = params.get("inventory") or ctx.extras.get("inventory")
    if not inventory:
        return ToolResult(ok=False, error="inventory required in params or context.extras")

    names = params.get("material_names") or ctx.extras.get("material_names") or {}
    safe = params.get("safe_levels") or ctx.extras.get("safe_levels") or {}

    report = check_jobs_material_static(
        jobs,
        inventory,
        material_names=names,
        safe_levels=safe,
    )
    if ctx.artifacts is not None:
        ctx.artifacts["material_check"] = report
    return ToolResult(ok=True, data=report, artifacts_key="material_check")


def register_material_check_static_tool() -> None:
    name = "material.check_static"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="开工前 BOM 静态齐套检查",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
