"""planning.strategy_generate — 从自然语言目标生成 SchedulingStrategy。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.strategy.generator import generate_strategy
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool

_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "user_goal": {"type": "string", "description": "自然语言排程策略目标"},
        "jobs": {"type": "array", "description": "工单列表"},
        "machines": {"type": "array", "description": "机器列表"},
        "workers": {"type": "array"},
        "tools": {"type": "array"},
        "allow_simulated": {"type": "boolean"},
    },
    "required": ["user_goal", "jobs", "machines"],
}

_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "strategy": {"type": "object"},
        "meta": {"type": "object"},
    },
}


def _handle_strategy_generate(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    user_goal = params.get("user_goal") or (ctx.extras or {}).get("user_goal") or ""
    jobs = params.get("jobs") or ctx.extras.get("jobs") or []
    machines = params.get("machines") or ctx.extras.get("machines") or []
    llm_client = params.get("llm_client") or ctx.extras.get("llm_client")

    strategy, meta = generate_strategy(
        user_goal=user_goal,
        jobs=jobs,
        machines=machines,
        llm_client=llm_client,
        workers=params.get("workers") or ctx.extras.get("workers"),
        tools=params.get("tools") or ctx.extras.get("tools"),
        allow_simulated=params.get("allow_simulated", True),
    )
    data = {"strategy": strategy.to_dict(), "meta": meta}
    if ctx.artifacts is not None:
        ctx.artifacts["strategy_draft"] = data
    return ToolResult(ok=True, data=data, artifacts_key="strategy_draft")


def register_strategy_generate_tool() -> None:
    name = "planning.strategy_generate"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="从自然语言目标生成参数化排程策略",
            input_schema=_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            handler=_handle_strategy_generate,
            risk_level="ask",
        )
    )
