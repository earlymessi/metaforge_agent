"""Photo dedication: bind later photo ops to mark machine, then reuse any solver."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from metaforge.fab.research._common import is_photo_task, jobs_to_problem
from metaforge.utils.compare_solvers import run_single_solver


def apply_dedication_bind(jobs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Fix machine_id on all photo tasks per lot after choosing mark machine."""
    bound = deepcopy(jobs)
    notes: List[str] = []
    next_pick = 0

    for job in bound:
        tasks = [t for t in (job.get("tasks") or []) if isinstance(t, dict)]
        photo = [t for t in tasks if is_photo_task(t)]
        if not photo:
            continue
        mark = next((t for t in photo if t.get("is_dedication_mark")), photo[0])
        options = list(mark.get("machine_options") or [])
        if mark.get("machine_id") is not None and int(mark["machine_id"]) not in [
            int(x) for x in options
        ]:
            options.insert(0, int(mark["machine_id"]))
        if not options:
            options = [0]
        chosen = int(options[next_pick % len(options)])
        next_pick += 1
        jid = job.get("job_id") or job.get("name")
        notes.append(f"lot {jid}: dedicated machine={chosen} (mark={mark.get('name')})")
        for t in photo:
            t["machine_id"] = chosen
            t["machine_options"] = [chosen]
    return bound, notes


def run_dedication_method(
    jobs: List[Dict[str, Any]],
    *,
    solver_id: str = "spt",
    solver_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    bound, notes = apply_dedication_bind(jobs)
    problem, name_map, _prio = jobs_to_problem(bound, instance_name="FAB Dedication")
    sr = run_single_solver(solver_id, problem, solver_params=solver_params)
    gantt = list(sr.gantt_data or [])
    for item in gantt:
        jid = item.get("job_id")
        if jid in name_map:
            item["job_name"] = name_map[jid]
    return {
        "jobs": bound,
        "gantt_data": gantt,
        "metrics": dict(sr.metrics or {}),
        "bind_notes": notes,
        "solver_id": solver_id,
        "schedule_id": f"dedication_bind_{solver_id}",
    }
