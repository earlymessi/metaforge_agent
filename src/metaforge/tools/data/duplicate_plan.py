"""data.duplicate_plan — 复制计划。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.services import plan_store
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.data._plan_nav import apply_active_plan, enrich_active_from_doc
from metaforge.tools.data._plan_resolve import resolve_plan_ref
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    doc, err = resolve_plan_ref(
        plan_id=params.get("plan_id"),
        query=params.get("query") or params.get("source_name"),
    )
    if err or not doc:
        return ToolResult(ok=False, error=err or "plan not found")

    new_name = (params.get("new_name") or "").strip() or None
    copied, err = plan_store.duplicate_plan(plan_id=str(doc["id"]), new_name=new_name)
    if err or not copied:
        return ToolResult(ok=False, error=err or "duplicate failed")

    active = enrich_active_from_doc(copied)
    apply_active_plan(ctx, active, action="duplicate", reason="复制计划")
    return ToolResult(ok=True, data=active, artifacts_key="active_plan")


def register_data_duplicate_plan_tool() -> None:
    name = "data.duplicate_plan"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="复制已有计划为新计划",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
