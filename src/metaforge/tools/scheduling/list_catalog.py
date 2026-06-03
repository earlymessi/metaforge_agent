"""scheduling.list_catalog — 策略模板与求解器目录。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.agent.scheduling_agent import STRATEGY_TEMPLATES
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool
from metaforge.utils.solver_registry import get_solver_catalog


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    family = params.get("family")
    catalog = get_solver_catalog(family=family)
    strategies = [
        {"id": t["id"], "name": t.get("name", t["id"]), "weights": dict(t.get("weights") or {})}
        for t in STRATEGY_TEMPLATES
    ]
    data = {
        "strategies": strategies,
        "solvers": catalog.get("solvers", []),
        "families": catalog.get("families", []),
    }
    if ctx.artifacts is not None:
        ctx.artifacts["scheduling_catalog"] = data
    return ToolResult(ok=True, data=data, artifacts_key="scheduling_catalog")


def register_scheduling_list_catalog_tool() -> None:
    name = "scheduling.list_catalog"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="列出可用排程策略与求解器（回答「有哪些算法/策略」）",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
