"""data.list_plans — 列出数据库中的计划。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.services import plan_store
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    limit = int(params.get("limit") or 30)
    plans, err = plan_store.list_plans(limit=limit)
    if err:
        return ToolResult(ok=False, error=err)
    summary = [
        {
            "id": p.get("id"),
            "plan_name": p.get("plan_name"),
            "job_count": len(p.get("jobs") or []),
            "status": p.get("status"),
        }
        for p in plans
    ]
    if ctx.artifacts is not None:
        ctx.artifacts["plan_list"] = summary
    return ToolResult(ok=True, data={"plans": summary, "count": len(summary)}, artifacts_key="plan_list")


def register_data_list_plans_tool() -> None:
    name = "data.list_plans"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="列出 MongoDB 中的计划/订单",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
