"""LLM Plan 纠偏（遗留调度 Plan 纠偏工具，供单测与兼容导入）。"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from metaforge.agents.base import AgentRequest, PlanStep
from metaforge.agents.persist_intent import wants_persist_request

_CATALOG_QUERY_RE = re.compile(
    r"有哪些算法|算法.*(?:目录|列表)|求解器.*(?:目录|列表)|支持什么算法",
    re.I,
)
_COMPARE_RUN_RE = re.compile(
    r"遗传|模拟退火|禁忌|SPT|对比.*算法|算法.*对比|对比一下|各跑一遍|和.*对比",
    re.I,
)
_FAST_RUN_RE = re.compile(r"快速|先出.*结果", re.I)
_RUN_PLAN_TOOLS = frozenset({"scheduling.parse_intent", "scheduling.run"})


def _wants_run_plan(message: str, params: Dict[str, Any]) -> bool:
    msg = (message or "").strip()
    if params.get("skip_parse") or params.get("_skip_vague_clarify"):
        return True
    if params.get("intent") == "schedule" or params.get("intent") == "pipeline":
        return True
    if _CATALOG_QUERY_RE.search(msg):
        return False
    if _COMPARE_RUN_RE.search(msg) or _FAST_RUN_RE.search(msg):
        return True
    if msg in ("排程", "排产") or (len(msg) <= 8 and "排" in msg and "计划" not in msg):
        return True
    return False


def _default_run_plan_steps(message: str) -> List[PlanStep]:
    return [
        PlanStep("s1", "scheduling.parse_intent", {"message": message}),
        PlanStep("s2", "scheduling.run", {}),
    ]


def _append_persist_steps(steps: List[PlanStep]) -> List[PlanStep]:
    out = list(steps)
    out.append(PlanStep("sp1", "delivery.assess", {}))
    out.append(PlanStep("sp2", "data.propose_persist", {}))
    return out


def _maybe_prepend_load_plan(steps: List[PlanStep], request: AgentRequest) -> List[PlanStep]:
    extras = request.context.get("extras") or {}
    if extras.get("loaded_plan_id") or request.context.get("plan_id"):
        return [PlanStep("s0", "data.load_plan", {})] + steps
    return steps


def coerce_scheduling_plan_steps(
    steps: List[PlanStep], request: AgentRequest
) -> List[PlanStep]:
    """LLM Plan 纠偏：对比/快速排程/显式 schedule 不应仅 list_catalog 或 ask_clarification。"""
    if request.params.get("confirm_token"):
        return steps
    tools = [s.tool for s in steps]
    if not _wants_run_plan(request.message or "", request.params):
        return steps
    if _RUN_PLAN_TOOLS.issubset(set(tools)):
        return steps
    if len(tools) == 1 and tools[0] == "scheduling.list_catalog":
        if _CATALOG_QUERY_RE.search(request.message or ""):
            return steps
    if "scheduling.ask_clarification" in tools or (
        len(tools) == 1 and tools[0] == "scheduling.list_catalog"
    ):
        out = _default_run_plan_steps(request.message or "")
        if wants_persist_request(request.message or "", request.params):
            out = _maybe_prepend_load_plan(out, request)
            return _append_persist_steps(out)
        return out
    return steps
