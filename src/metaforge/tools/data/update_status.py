"""data.update_status — 更新计划状态 pending/done/archived。"""



from __future__ import annotations



from typing import Any, Dict



from metaforge.services import plan_store

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec

from metaforge.tools.data._plan_nav import apply_active_plan, enrich_active_from_doc

from metaforge.tools.data._plan_resolve import resolve_plan_ref

from metaforge.tools.registry import get_tool, register_tool





def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:

    status = (params.get("status") or "").strip().lower()

    if not status:

        return ToolResult(ok=False, error="status required")



    doc, err = resolve_plan_ref(

        plan_id=params.get("plan_id") or ctx.plan_id,

        query=params.get("query") or params.get("plan_name"),

    )

    if err or not doc:

        return ToolResult(ok=False, error=err or "plan not found")



    updated, err = plan_store.update_status(plan_id=str(doc["id"]), status=status)

    if err or not updated:

        return ToolResult(ok=False, error=err or "update failed")



    active = enrich_active_from_doc(updated)

    apply_active_plan(ctx, active, action="update_status", reason="更新计划状态")

    data = {

        "plan_id": active.get("plan_id"),

        "plan_name": active.get("plan_name"),

        "status": updated.get("status"),

    }

    if ctx.artifacts is not None:

        ctx.artifacts["plan_status_update"] = data

    return ToolResult(ok=True, data=data, artifacts_key="plan_status_update")





def register_data_update_status_tool() -> None:

    name = "data.update_status"

    try:

        get_tool(name)

        return

    except KeyError:

        pass

    register_tool(

        ToolSpec(

            name=name,

            description_zh="更新计划状态（pending/done/archived）",

            input_schema={"type": "object"},

            output_schema={"type": "object"},

            handler=_handle,

        )

    )


