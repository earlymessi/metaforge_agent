"""排程意图类型与置信度常量。

``detect_list_intent`` 仅用于 ``LLM_ENABLED=0`` 或 GLM 失败后的离线回退；
在线主路径由 ``scheduling_*`` prompt 输出 ``LIST_SOLVERS`` / ``LIST_STRATEGIES``。
"""

from __future__ import annotations

from enum import Enum


class ScheduleIntentType(str, Enum):
    RUN_SCHEDULE = "RUN_SCHEDULE"
    COMPARE_SOLVERS = "COMPARE_SOLVERS"
    RUN_BENCHMARK = "RUN_BENCHMARK"
    LIST_SOLVERS = "LIST_SOLVERS"
    LIST_STRATEGIES = "LIST_STRATEGIES"
    GET_LAST_RESULT = "GET_LAST_RESULT"
    SET_DEFAULT_STRATEGY = "SET_DEFAULT_STRATEGY"
    SET_DEFAULT_SOLVER = "SET_DEFAULT_SOLVER"
    TOGGLE_MATERIAL = "TOGGLE_MATERIAL"
    CLARIFICATION = "CLARIFICATION"
    HELP = "HELP"
    UNKNOWN = "UNKNOWN"


CONFIDENCE_HIGH = 0.95
CONFIDENCE_EXECUTE = 0.7
CONFIDENCE_CLARIFY = 0.4
FAST_MAKESPAN_BOOST = 1.5
FAST_COMPARE_MAX_SOLVERS = 6
RL_EXCLUDED_FAMILIES = frozenset({"rl"})

_LIST_SOLVER_PATTERNS = ("有哪些算法", "有哪些策略", "有哪些求解器", "算法列表", "求解器", "支持什么算法")
_LIST_STRATEGY_PATTERNS = ("策略列表", "有哪些策略模板", "优化目标有哪些")


def detect_list_intent(message: str) -> ScheduleIntentType | None:
    """离线回退：列出算法/策略目录（非 LLM 主路径）。"""
    text = (message or "").strip()
    if not text:
        return None
    if any(p in text for p in _LIST_STRATEGY_PATTERNS) and "算法" not in text:
        return ScheduleIntentType.LIST_STRATEGIES
    if any(p in text for p in _LIST_SOLVER_PATTERNS):
        return ScheduleIntentType.LIST_SOLVERS
    return None


def normalize_intent_type(value: str | None) -> ScheduleIntentType:
    if not value:
        return ScheduleIntentType.RUN_SCHEDULE
    key = str(value).strip().upper()
    try:
        return ScheduleIntentType(key)
    except ValueError:
        return ScheduleIntentType.RUN_SCHEDULE
