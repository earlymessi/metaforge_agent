"""待办会话任务注册表 — 路由续聊时统一查询，无需各 Agent 硬编码。"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from metaforge.memory.manager import MemoryManager
from metaforge.memory.types import WORKING_KEY_INSERT_JOB

PendingCheck = Callable[[MemoryManager], bool]


def _insert_job_need_input(mm: MemoryManager) -> bool:
    ns, key = WORKING_KEY_INSERT_JOB
    intake = mm.get_working(ns, key)
    return isinstance(intake, dict) and intake.get("status") == "need_input"


def _scheduling_clarification(mm: MemoryManager) -> bool:
    sched = mm.get_scheduling()
    pending = sched.get("pending_clarification")
    if not isinstance(pending, dict):
        return False
    exp = float(pending.get("expires_at_ts") or 0)
    if exp and time.time() > exp:
        return False
    return True


# (agent_id, intent, reason_zh, checker)
PENDING_TASKS: List[tuple[str, str, str, PendingCheck]] = [
    (
        "events",
        "reschedule",
        "会话待补全插单工艺，继续异常重排 Agent",
        _insert_job_need_input,
    ),
    (
        "scheduling",
        "schedule",
        "会话待选定排程目标，继续智能排程 Agent",
        _scheduling_clarification,
    ),
]


def has_pending_session_task(context: Optional[Dict[str, Any]]) -> bool:
    mm = MemoryManager.from_context(context)
    return any(fn(mm) for _, _, _, fn in PENDING_TASKS)


def pending_route_hint(context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """返回应续聊的 agent 路由片段（与 resolve_agent_route 字段兼容）。"""
    from metaforge.orchestrator.router import ROUTER_BUILD_ID

    mm = MemoryManager.from_context(context)
    for agent_id, intent, reason_zh, checker in PENDING_TASKS:
        if checker(mm):
            return {
                "agent_id": agent_id,
                "router": "session_continue",
                "intent": intent,
                "rule_reason_zh": reason_zh,
                "router_build_id": ROUTER_BUILD_ID,
            }
    return None
