"""events.merge_insert_job — 将用户补充话术合并进插单草稿。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.events.insert_job_intake import (
    apply_intake_to_envelope,
    assess_insert_order_envelope,
    merge_insert_job_followup,
    message_looks_like_insert_order,
)
from metaforge.orchestrator.router import has_pending_insert_job_intake
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    message = params.get("message") or ctx.extras.get("message") or ""
    if not message.strip():
        return ToolResult(ok=False, error="message required")

    artifacts = ctx.artifacts or {}
    intake = artifacts.get("insert_job_intake") or {}
    if not has_pending_insert_job_intake({"artifacts": artifacts}):
        return ToolResult(
            ok=True,
            data={"status": "skipped", "reason_zh": "非插单续聊，跳过 merge"},
        )

    envelope = dict(artifacts.get("event_envelope") or {})
    if message_looks_like_insert_order(message):
        envelope["event_type"] = "insert_order"
    elif not envelope.get("event_type"):
        envelope["event_type"] = "insert_order"
        envelope.setdefault("params", dict(intake.get("params_snapshot") or {}))

    draft = intake.get("draft") or (envelope.get("params") or {}).get("insert_job") or {}
    merged = merge_insert_job_followup(message, draft)
    envelope = apply_intake_to_envelope(envelope, merged)
    reassessed = assess_insert_order_envelope(envelope, original_message=message)

    if ctx.artifacts is not None:
        ctx.artifacts["event_envelope"] = envelope
        ctx.artifacts["insert_job_intake"] = reassessed

    return ToolResult(ok=True, data=reassessed, artifacts_key="insert_job_intake")


def register_events_merge_insert_job_tool() -> None:
    name = "events.merge_insert_job"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="合并用户补充的插单工序/机台/时长到 event_envelope",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
