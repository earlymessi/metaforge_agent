"""scheduling.ask_clarification — 返回澄清问题，不执行排程。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool

_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "clarification_context": {"type": "object"},
        "intent_type": {"type": "string"},
    },
}

_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "context": {"type": "object"},
        "intent_type": {"type": "string"},
    },
}


def _handle_ask_clarification(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    pre = (ctx.extras or {}).get("_pre_resolved") or (params.get("_pre_resolved"))
    if isinstance(pre, dict):
        question = pre.get("clarification_question") or pre.get("summary_zh") or ""
        clar_ctx = pre.get("clarification_context") or {}
        itype = pre.get("intent_type") or "CLARIFICATION"
    else:
        question = params.get("question") or ""
        clar_ctx = params.get("clarification_context") or {}
        itype = params.get("intent_type") or "CLARIFICATION"

    if not question:
        interp = (ctx.artifacts or {}).get("interpretation") or {}
        question = interp.get("clarification_question") or interp.get("summary_zh") or "请补充排程需求。"
        clar_ctx = interp.get("clarification_context") or clar_ctx
        itype = interp.get("intent_type") or itype

    payload = {
        "question": question,
        "context": clar_ctx,
        "intent_type": itype,
    }
    if ctx.artifacts is not None:
        ctx.artifacts["clarification"] = payload
        if isinstance(pre, dict):
            ctx.artifacts["interpretation"] = pre
    return ToolResult(ok=True, data=payload, artifacts_key="clarification")


def register_ask_clarification_tool() -> None:
    name = "scheduling.ask_clarification"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="向用户提出澄清问题（阻塞式，不执行排程计算）",
            input_schema=_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            handler=_handle_ask_clarification,
        )
    )

