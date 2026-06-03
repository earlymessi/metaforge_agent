"""data.bind_plan — 按名称或 ID 绑定计划到上下文。"""



from __future__ import annotations



from typing import Any, Dict



from metaforge.services import plan_store

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec

from metaforge.tools.data._plan_nav import apply_active_plan, enrich_active_from_doc

from metaforge.tools.registry import get_tool, register_tool





def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:

    plan_id = params.get("plan_id")

    query = (params.get("query") or params.get("plan_name") or "").strip()



    doc = None

    if plan_id:

        doc, err = plan_store.get_plan(str(plan_id))

        if err:

            return ToolResult(ok=False, error=err)

    elif query:

        found, err = plan_store.find_by_query(query)

        if err:

            return ToolResult(ok=False, error=err)

        if not found:

            return ToolResult(ok=False, error=f"plan not found: {query}")

        if isinstance(found, dict) and found.get("ambiguous"):

            names = [p.get("plan_name") for p in found.get("matches", [])[:5]]

            return ToolResult(ok=False, error=f"ambiguous plan: {', '.join(names)}")

        doc = found

    else:

        return ToolResult(ok=False, error="plan_id or query required")



    active = enrich_active_from_doc(doc)

    navigate = bool(params.get("navigate_aps", True))

    apply_active_plan(ctx, active, navigate=navigate, reason="绑定计划")

    return ToolResult(ok=True, data=active, artifacts_key="active_plan")





def register_data_bind_plan_tool() -> None:

    name = "data.bind_plan"

    try:

        get_tool(name)

        return

    except KeyError:

        pass

    register_tool(

        ToolSpec(

            name=name,

            description_zh="加载/绑定已有计划",

            input_schema={"type": "object"},

            output_schema={"type": "object"},

            handler=_handle,

        )

    )


