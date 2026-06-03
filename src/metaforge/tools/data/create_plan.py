"""data.create_plan — 在数据库中新建计划。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.plans.intent import parse_plan_intent
from metaforge.services import plan_store
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    plan_name = (params.get("plan_name") or "").strip()
    if not plan_name:
        parsed = parse_plan_intent(str(ctx.extras.get("message") or ""))
        if parsed and parsed.get("action") == "create":
            plan_name = (parsed.get("plan_name") or "").strip()
    if not plan_name:
        return ToolResult(ok=False, error="plan_name required")

    jobs = params.get("jobs")
    if jobs is None:
        # 对话「新建计划」默认空工单池，由用户在排程中心编辑；勿带入会话中的 custom_data
        jobs = []
    elif not isinstance(jobs, list):
        jobs = []

    doc, err = plan_store.create_plan(plan_name=plan_name, jobs=jobs)
    if err:
        return ToolResult(ok=False, error=err)

    active = {
        "plan_id": doc.get("id"),
        "plan_name": doc.get("plan_name"),
        "jobs": doc.get("jobs") or [],
        "job_count": len(doc.get("jobs") or []),
        "plan_status": doc.get("status"),
        "has_schedule": bool(doc.get("schedule_results") or doc.get("schedule_result")),
    }
    from metaforge.tools.data._plan_nav import apply_active_plan

    apply_active_plan(ctx, active, action="create", reason="新建计划")
    return ToolResult(ok=True, data=active, artifacts_key="active_plan")


def register_data_create_plan_tool() -> None:
    name = "data.create_plan"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="新建计划并写入数据库",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
