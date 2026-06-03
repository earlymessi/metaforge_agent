"""scheduling.parse_intent — 封装 resolve_schedule_intent。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.scheduling.resolve_intent import resolve_schedule_intent
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool

_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "message": {"type": "string", "description": "自然语言排程描述"},
        "solvers": {"type": "array", "items": {"type": "string"}},
        "weights": {"type": "object"},
        "strategy_id": {"type": "string"},
        "enforce_material": {"type": "boolean"},
        "benchmark_file": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "solvers": {"type": "array"},
        "weights": {"type": "object"},
        "strategy_id": {"type": "string"},
        "strategy_name": {"type": "string"},
        "enforce_material": {"type": "boolean"},
        "benchmark_file": {"type": ["string", "null"]},
        "summary_zh": {"type": "string"},
        "intent_type": {"type": "string"},
        "confidence": {"type": "number"},
        "is_fast_mode": {"type": "boolean"},
        "clarification_question": {"type": ["string", "null"]},
    },
}


def _handle_parse_intent(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    pre = params.get("_pre_resolved") or (ctx.extras or {}).get("_pre_resolved")
    if isinstance(pre, dict):
        data = dict(pre)
    else:
        merge_params = dict(params)
        if not merge_params.get("message"):
            merge_params["message"] = ctx.extras.get("message") or ""
        session_id = (
            params.get("session_id")
            or (ctx.extras or {}).get("session_id")
            or (ctx.extras or {}).get("sessionId")
        )
        data = resolve_schedule_intent(
            merge_params,
            extras=ctx.extras,
            benchmark_file=params.get("benchmark_file") or ctx.benchmark_file,
            session_id=session_id,
        )
    data["compare_kwargs"] = {
        "solvers": data["solvers"],
        "weights": data["weights"],
        "enforce_material": data["enforce_material"],
        "benchmark_file": data.get("benchmark_file"),
    }
    if ctx.artifacts is not None:
        ctx.artifacts["interpretation"] = data
    return ToolResult(ok=True, data=data, artifacts_key="interpretation")


def register_parse_intent_tool() -> None:
    name = "scheduling.parse_intent"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="解析自然语言或参数，匹配排程算法与策略权重",
            input_schema=_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            handler=_handle_parse_intent,
        )
    )

