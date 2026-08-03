"""Rule-based Order Agent: critical / due-risk / priority adjustments."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from metaforge.planning_collab.protocol import AgentResult, AgentTask

# Jobs with due_date at or below this threshold are treated as near-due.
_DUE_RISK_WINDOW = 20
# Jobs with priority at or above this get a priority adjustment boost.
_HIGH_PRIORITY = 5

# Short order/customer id: letters, digits, underscore (no Chinese suffixes).
_ID_TOKEN = r"[A-Za-z0-9_]+"
# Clip accidental Chinese suffixes when a broader capture is used.
_KEY_TERMINATORS = ("按期", "交付", "完成")


def _clip_key(raw: str) -> str:
    """Normalize a captured key: strip fillers and truncate at terminators."""
    token = (raw or "").strip()
    for prefix in ("保证", "客户"):
        if token.startswith(prefix):
            token = token[len(prefix) :].strip()
    for term in _KEY_TERMINATORS:
        idx = token.find(term)
        if idx >= 0:
            token = token[:idx].strip()
    if token in {"保证", "客户", "优先"}:
        return ""
    return token


def _goal_critical_keys(user_goal: str) -> Set[str]:
    """Extract customer / order keys mentioned in the user goal."""
    keys: Set[str] = set()
    if not user_goal:
        return keys

    for m in re.finditer(r"保证(?:客户)?(.+?)按期", user_goal):
        keys.add(_clip_key(m.group(1)))

    for m in re.finditer(rf"客户({_ID_TOKEN})", user_goal):
        keys.add(_clip_key(m.group(1)))

    for m in re.finditer(rf"优先(?:保证)?(?:客户)?({_ID_TOKEN})", user_goal):
        keys.add(_clip_key(m.group(1)))

    return {k for k in keys if k}

def _job_matches_key(job: Dict[str, Any], keys: Set[str]) -> bool:
    job_id = str(job.get("job_id") or "")
    customer = str(job.get("customer") or "")
    return bool(keys) and (job_id in keys or customer in keys)


def run_order_agent(task: AgentTask) -> AgentResult:
    """Analyze jobs for critical / due-risk / priority signals (pure rules)."""
    inputs = task.inputs or {}
    user_goal = str(inputs.get("user_goal") or "")
    jobs: List[Dict[str, Any]] = list(inputs.get("jobs") or [])

    goal_keys = _goal_critical_keys(user_goal)

    critical: List[str] = []
    due_risk: List[str] = []
    overdue: List[str] = []
    priority_adjustments: Dict[str, int] = {}
    warnings: List[str] = []

    for job in jobs:
        job_id = str(job.get("job_id") or "")
        if not job_id:
            warnings.append("skip job without job_id")
            continue

        due_date = job.get("due_date")
        priority = job.get("priority")
        try:
            due_val = float(due_date) if due_date is not None else None
        except (TypeError, ValueError):
            due_val = None
            warnings.append(f"{job_id}: invalid due_date")

        try:
            pri_val = int(priority) if priority is not None else 0
        except (TypeError, ValueError):
            pri_val = 0
            warnings.append(f"{job_id}: invalid priority")

        if _job_matches_key(job, goal_keys):
            if job_id not in critical:
                critical.append(job_id)

        if due_val is not None:
            if due_val < 0:
                overdue.append(job_id)
            elif due_val <= _DUE_RISK_WINDOW:
                due_risk.append(job_id)

        if pri_val >= _HIGH_PRIORITY:
            priority_adjustments[job_id] = pri_val
            if job_id not in critical and pri_val >= _HIGH_PRIORITY + 3:
                critical.append(job_id)

    summary_parts = [
        f"critical={len(critical)}",
        f"due_risk={len(due_risk)}",
        f"overdue={len(overdue)}",
        f"priority_adj={len(priority_adjustments)}",
    ]
    summary = "订单分析: " + ", ".join(summary_parts)

    return AgentResult(
        agent_id="order",
        status="success",
        summary=summary,
        artifacts={
            "critical_orders": critical,
            "due_risk_orders": due_risk,
            "overdue_orders": overdue,
            "priority_adjustments": priority_adjustments,
        },
        warnings=warnings,
        reasoning_summary=None,
    )
