"""data.load_plan — 加载计划工单到上下文。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    jobs = params.get("jobs") or ctx.custom_data
    if not jobs:
        return ToolResult(ok=False, error="jobs or context.custom_data required")

    plan_id = params.get("plan_id") or ctx.extras.get("loaded_plan_id") or ctx.plan_id
    plan_name = params.get("plan_name") or ctx.extras.get("plan_name") or "未命名计划"
    loaded = {
        "plan_id": plan_id,
        "plan_name": plan_name,
        "jobs": jobs,
        "job_count": len(jobs),
    }
    if ctx.artifacts is not None:
        ctx.artifacts["loaded_plan"] = loaded
    return ToolResult(ok=True, data=loaded, artifacts_key="loaded_plan")


def register_data_load_plan_tool() -> None:
    name = "data.load_plan"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="加载计划工单（通常由 API 预填 custom_data）",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
