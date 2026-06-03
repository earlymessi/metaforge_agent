"""events.check_insert_job — 校验插单工艺是否齐全，不齐则 need_input。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.events.insert_job_intake import (
    apply_intake_to_envelope,
    assess_insert_order_envelope,
)
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    envelope = (ctx.artifacts or {}).get("event_envelope")
    if not envelope or envelope.get("event_type") != "insert_order":
        data = {"status": "not_applicable", "ready": True}
        return ToolResult(ok=True, data=data)

    message = params.get("message") or ctx.extras.get("message") or ""
    intake = assess_insert_order_envelope(envelope, original_message=message)
    if intake.get("ready"):
        env2 = apply_intake_to_envelope(envelope, intake["draft"])
        if ctx.artifacts is not None:
            ctx.artifacts["event_envelope"] = env2
        intake["status"] = "ready"
    if ctx.artifacts is not None:
        ctx.artifacts["insert_job_intake"] = intake
    return ToolResult(ok=True, data=intake, artifacts_key="insert_job_intake")


def register_events_check_insert_job_tool() -> None:
    name = "events.check_insert_job"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="校验插单 insert_job 是否完整；不完整返回追问文案",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
