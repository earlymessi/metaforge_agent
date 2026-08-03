"""planning.strategy_validate — 校验 SchedulingStrategy 合法性。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.strategy.guardrails import validate_strategy
from metaforge.strategy.models import SchedulingStrategy
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool

_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "strategy": {"type": "object", "description": "SchedulingStrategy JSON"},
        "jobs": {"type": "array"},
        "machines": {"type": "array"},
        "workers": {"type": "array"},
        "tools": {"type": "array"},
        "allow_simulated": {"type": "boolean"},
    },
    "required": ["strategy", "jobs", "machines"],
}

_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "errors": {"type": "array", "items": {"type": "string"}},
        "strategy": {"type": "object"},
    },
}


def _handle_strategy_validate(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    raw = params.get("strategy")
    if not isinstance(raw, dict):
        return ToolResult(ok=False, error="strategy must be an object")

    strategy = SchedulingStrategy.from_dict(raw)
    jobs = params.get("jobs") or ctx.extras.get("jobs") or []
    machines = params.get("machines") or ctx.extras.get("machines") or []

    ok, errors, fixed = validate_strategy(
        strategy,
        jobs=jobs,
        machines=machines,
        workers=params.get("workers") or ctx.extras.get("workers"),
        tools=params.get("tools") or ctx.extras.get("tools"),
        allow_simulated=params.get("allow_simulated", True),
    )
    return ToolResult(
        ok=True,
        data={"ok": ok, "errors": errors, "strategy": fixed.to_dict()},
    )


def register_strategy_validate_tool() -> None:
    name = "planning.strategy_validate"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="校验排程策略硬/软约束与资源引用",
            input_schema=_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            handler=_handle_strategy_validate,
        )
    )
