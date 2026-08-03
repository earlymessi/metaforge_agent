"""Rule-based Constraint Agent: hard/soft candidates from goal + order analysis."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from metaforge.planning_collab.protocol import AgentResult, AgentTask
from metaforge.strategy.catalog import HARD_CONSTRAINT_TYPES, SOFT_CONSTRAINT_TYPES

_CHANGEOVER_HINTS = ("减少换型", "少换型", "换型", "setup", "changeover")

_ID_TOKEN = r"[A-Za-z0-9_]+"
_KEY_TERMINATORS = ("按期", "交付", "完成")


def _clip_key(raw: str) -> str:
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


def _due_for_job(job: Dict[str, Any]) -> Any:
    if "due_date" in job:
        return job.get("due_date")
    return job.get("due")


def _filter_typed(
    items: List[Dict[str, Any]],
    allowed: Set[str],
    warnings: List[str],
) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    for item in items:
        ctype = str(item.get("type") or "")
        if ctype not in allowed:
            warnings.append(f"discard unknown constraint type: {ctype}")
            continue
        kept.append(item)
    return kept


def run_constraint_agent(task: AgentTask) -> AgentResult:
    """Propose hard/soft constraints (pure rules; types ∈ S1 catalog)."""
    inputs = task.inputs or {}
    user_goal = str(inputs.get("user_goal") or "")
    jobs: List[Dict[str, Any]] = list(inputs.get("jobs") or [])
    order_analysis = inputs.get("order_analysis") or {}
    if not isinstance(order_analysis, dict):
        order_analysis = {}

    warnings: List[str] = []
    hard: List[Dict[str, Any]] = []
    soft: List[Dict[str, Any]] = []

    critical_ids: List[str] = []
    for jid in order_analysis.get("critical_orders") or []:
        sid = str(jid)
        if sid and sid not in critical_ids:
            critical_ids.append(sid)

    goal_keys = _goal_critical_keys(user_goal)
    jobs_by_id: Dict[str, Dict[str, Any]] = {}
    for job in jobs:
        job_id = str(job.get("job_id") or "")
        if not job_id:
            continue
        jobs_by_id[job_id] = job
        if _job_matches_key(job, goal_keys) and job_id not in critical_ids:
            critical_ids.append(job_id)

    for job_id in critical_ids:
        constraint: Dict[str, Any] = {"type": "order_on_time", "job_id": job_id}
        job = jobs_by_id.get(job_id)
        if job is not None:
            due = _due_for_job(job)
            if due is not None:
                constraint["due_date"] = due
        hard.append(constraint)

    if any(h in user_goal for h in _CHANGEOVER_HINTS):
        soft.append({"type": "reduce_changeover"})

    for raw in inputs.get("proposed_hard") or []:
        if isinstance(raw, dict):
            hard.append(dict(raw))
    for raw in inputs.get("proposed_soft") or []:
        if isinstance(raw, dict):
            soft.append(dict(raw))

    hard = _filter_typed(hard, HARD_CONSTRAINT_TYPES, warnings)
    soft = _filter_typed(soft, SOFT_CONSTRAINT_TYPES, warnings)

    summary = (
        f"约束分析: hard={len(hard)}, soft={len(soft)}, "
        f"order_on_time={sum(1 for c in hard if c.get('type') == 'order_on_time')}"
    )

    return AgentResult(
        agent_id="constraint",
        status="success",
        summary=summary,
        artifacts={
            "hard_constraints": hard,
            "soft_constraints": soft,
        },
        warnings=warnings,
        reasoning_summary=None,
    )
