"""Timelink-aware preprocess, then reuse any MetaForge solver."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from metaforge.fab.research._common import jobs_to_problem
from metaforge.utils.compare_solvers import run_single_solver


def _timelinks(fab_meta: Optional[Dict[str, Any]], strategy_defaults: Dict[str, Any]) -> List[Dict[str, Any]]:
    links = list((fab_meta or {}).get("timelinks") or [])
    for c in strategy_defaults.get("hard_constraints") or []:
        if not isinstance(c, dict):
            continue
        if c.get("type") != "max_lag_between_ops":
            continue
        links.append(
            {
                "from_op": c.get("from_op"),
                "to_op": c.get("to_op"),
                "max_lag": c.get("max_lag", c.get("max_lag_hours")),
            }
        )
    return [x for x in links if x.get("from_op") and x.get("to_op") and x.get("max_lag") is not None]


def apply_timelink_priorities(
    jobs: List[Dict[str, Any]],
    links: List[Dict[str, Any]],
    *,
    mode: str = "slack",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    out = deepcopy(jobs)
    notes: List[str] = []
    if not links:
        notes.append("no timelinks; falling back to plain solver decode")
        return out, notes

    min_lag = min(float(l["max_lag"]) for l in links)
    for job in out:
        names = {str(t.get("name") or "") for t in (job.get("tasks") or []) if isinstance(t, dict)}
        involved = any(
            str(l["from_op"]) in names and str(l["to_op"]) in names for l in links
        )
        if not involved:
            continue
        base = int(job.get("priority") or 10)
        if mode == "edd":
            boost = int(max(1, 100 / max(min_lag, 0.1)))
            job["priority"] = base + boost
            if job.get("due_date") is None:
                job["due_date"] = float(min_lag) * 10
            notes.append(
                f"lot {job.get('job_id') or job.get('name')}: EDD/timelink boost→{job['priority']}"
            )
        else:
            boost = int(max(5, 50 / max(min_lag, 0.1)))
            job["priority"] = base + boost
            notes.append(
                f"lot {job.get('job_id') or job.get('name')}: slack urgency boost→{job['priority']}"
            )
    return out, notes


def run_timelink_method(
    jobs: List[Dict[str, Any]],
    *,
    fab_meta: Optional[Dict[str, Any]] = None,
    strategy_defaults: Optional[Dict[str, Any]] = None,
    mode: str = "slack",
    solver_id: str = "spt",
    solver_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    links = _timelinks(fab_meta, strategy_defaults or {})
    tuned, notes = apply_timelink_priorities(jobs, links, mode=mode)
    problem, name_map, _ = jobs_to_problem(tuned, instance_name="FAB Timelink")
    sr = run_single_solver(solver_id, problem, solver_params=solver_params)
    gantt = list(sr.gantt_data or [])
    for item in gantt:
        jid = item.get("job_id")
        if jid in name_map:
            item["job_name"] = name_map[jid]
    return {
        "jobs": tuned,
        "gantt_data": gantt,
        "metrics": dict(sr.metrics or {}),
        "timelink_notes": notes,
        "links": links,
        "solver_id": solver_id,
        "schedule_id": f"timelink_{mode}_{solver_id}",
    }
