"""execution.get_state — 读取 MES 当前执行态。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    doc = (ctx.extras or {}).get("production_execution")
    if not doc or doc.get("status") not in ("running", "paused"):
        idle = {
            "status": "idle",
            "hint_zh": "未启动 MES 执行；将使用已绑定计划的工单与排程快照重排。",
        }
        if ctx.artifacts is not None:
            ctx.artifacts["production_execution"] = idle
        return ToolResult(ok=True, data=idle, artifacts_key="production_execution")
    if ctx.artifacts is not None:
        ctx.artifacts["production_execution"] = doc
    return ToolResult(ok=True, data=doc, artifacts_key="production_execution")


def register_execution_get_state_tool() -> None:
    name = "execution.get_state"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="读取 MES 当前执行计划与仿真时刻",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
