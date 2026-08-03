"""planning.run — 执行完整策略规划流水线。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.strategy.pipeline import run_planning
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool

_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "user_goal": {"type": "string", "description": "自然语言排程策略目标"},
        "jobs": {"type": "array", "description": "工单列表"},
        "machines": {"type": "array", "description": "机器列表"},
        "skip_strategy_hitl": {"type": "boolean", "description": "跳过策略 HITL 审批"},
        "allow_simulated": {"type": "boolean"},
        "workers": {"type": "array"},
        "tools": {"type": "array"},
    },
    "required": ["user_goal", "jobs", "machines"],
}

_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "run_id": {"type": "string"},
        "status": {"type": "string"},
        "package": {"type": "object"},
        "strategy_draft": {"type": "object"},
        "evaluation": {"type": "object"},
    },
}


def _handle_planning_run(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    user_goal = params.get("user_goal") or (ctx.extras or {}).get("user_goal") or ""
    jobs = params.get("jobs") or ctx.extras.get("jobs") or []
    machines = params.get("machines") or ctx.extras.get("machines") or []
    skip_hitl = bool(params.get("skip_strategy_hitl", False))
    llm_client = params.get("llm_client") or ctx.extras.get("llm_client")
    problem = params.get("problem") or ctx.extras.get("problem")

    result = run_planning(
        user_goal=user_goal,
        jobs=jobs,
        machines=machines,
        skip_strategy_hitl=skip_hitl,
        llm_client=llm_client,
        problem=problem,
        workers=params.get("workers") or ctx.extras.get("workers"),
        tools=params.get("tools") or ctx.extras.get("tools"),
        allow_simulated=params.get("allow_simulated", True),
    )
    if ctx.artifacts is not None:
        ctx.artifacts["planning_run"] = result
    return ToolResult(ok=True, data=result, artifacts_key="planning_run")


def register_planning_run_tool() -> None:
    name = "planning.run"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="执行策略生成、求解与评估的完整规划流水线",
            input_schema=_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            handler=_handle_planning_run,
            risk_level="ask",
        )
    )
