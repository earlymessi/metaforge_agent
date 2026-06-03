"""data.rename_plan — 重命名计划。"""



from __future__ import annotations



from typing import Any, Dict



from metaforge.services import plan_store

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec

from metaforge.tools.data._plan_nav import apply_active_plan, enrich_active_from_doc

from metaforge.tools.data._plan_resolve import resolve_plan_ref

from metaforge.tools.registry import get_tool, register_tool





def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:

    new_name = (params.get("new_name") or params.get("plan_name") or "").strip()

    if not new_name:

        return ToolResult(ok=False, error="new_name required")



    doc, err = resolve_plan_ref(

        plan_id=params.get("plan_id"),

        query=params.get("query") or params.get("old_name"),

    )

    if err or not doc:

        return ToolResult(ok=False, error=err or "plan not found")



    updated, err = plan_store.rename_plan(plan_id=str(doc["id"]), new_name=new_name)

    if err or not updated:

        return ToolResult(ok=False, error=err or "rename failed")



    active = enrich_active_from_doc(updated)

    apply_active_plan(ctx, active, action="rename", reason="重命名计划")

    return ToolResult(ok=True, data=active, artifacts_key="active_plan")





def register_data_rename_plan_tool() -> None:

    name = "data.rename_plan"

    try:

        get_tool(name)

        return

    except KeyError:

        pass

    register_tool(

        ToolSpec(

            name=name,

            description_zh="按 ID 或名称重命名计划",

            input_schema={"type": "object"},

            output_schema={"type": "object"},

            handler=_handle,

        )

    )


