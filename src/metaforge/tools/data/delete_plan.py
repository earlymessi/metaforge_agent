"""data.delete_plan — 删除计划。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.services import plan_store
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    plan_id = params.get("plan_id")
    query = (params.get("query") or params.get("plan_name") or "").strip()

    if not plan_id and query:
        found, err = plan_store.find_by_query(query)
        if err:
            return ToolResult(ok=False, error=err)
        if not found:
            return ToolResult(ok=False, error=f"plan not found: {query}")
        if isinstance(found, dict) and found.get("ambiguous"):
            names = [p.get("plan_name") for p in found.get("matches", [])[:5]]
            return ToolResult(ok=False, error=f"ambiguous plan: {', '.join(names)}")
        plan_id = found.get("id")

    if not plan_id:
        return ToolResult(ok=False, error="plan_id or query required")

    ok, err = plan_store.delete_plan(plan_id=str(plan_id))
    if not ok:
        return ToolResult(ok=False, error=err or "delete failed")
    return ToolResult(ok=True, data={"deleted_plan_id": str(plan_id)})


def register_data_delete_plan_tool() -> None:
    name = "data.delete_plan"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="按 ID 或名称删除计划",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
