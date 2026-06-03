"""events.list_event_types — 支持的动态事件类型说明。"""

from __future__ import annotations

from typing import Any, Dict, List

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool

_EVENT_CATALOG: List[Dict[str, Any]] = [
    {
        "event_type": "insert_order",
        "name_zh": "插单",
        "status": "implemented",
        "params_hint": "insert_job, mode: local_repair|global",
    },
    {
        "event_type": "machine_breakdown",
        "name_zh": "设备故障",
        "status": "implemented",
        "params_hint": "machine_id(0起), breakdown_start, breakdown_duration",
    },
    {
        "event_type": "due_date_change",
        "name_zh": "改交期",
        "status": "implemented",
        "params_hint": "due_date_changes: [{job_name, new_due_date}]",
    },
    {
        "event_type": "planned_downtime",
        "name_zh": "计划停机",
        "status": "implemented",
        "params_hint": "downtime_blocks: [{machine_id, start, end, label}]",
    },
    {
        "event_type": "material_delay",
        "name_zh": "物料晚到",
        "status": "implemented",
        "params_hint": "job_name, delay_hours 或 material_arrival",
    },
    {
        "event_type": "priority_change",
        "name_zh": "调整优先级",
        "status": "implemented",
        "params_hint": "changes: [{job_name, new_priority}]",
    },
    {
        "event_type": "order_cancel",
        "name_zh": "撤单/暂停",
        "status": "implemented",
        "params_hint": "job_names: []",
    },
    {
        "event_type": "quantity_change",
        "name_zh": "数量变更",
        "status": "implemented",
        "params_hint": "changes: [{job_name, new_quantity}]",
    },
]


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    data = {"event_types": list(_EVENT_CATALOG), "count": len(_EVENT_CATALOG)}
    if ctx.artifacts is not None:
        ctx.artifacts["event_type_catalog"] = data
    return ToolResult(ok=True, data=data, artifacts_key="event_type_catalog")


def register_events_list_event_types_tool() -> None:
    name = "events.list_event_types"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="列出系统支持的异常/重排事件类型及参数说明",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
