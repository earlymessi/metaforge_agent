from __future__ import annotations

from typing import Any, Dict, List, Tuple

from metaforge.strategy.models import SchedulingStrategy
from metaforge.utils.problem_builder import build_problem_from_custom_jobs


def jobs_to_problem(jobs: List[Dict[str, Any]], instance_name: str = "FAB Research"):
    return build_problem_from_custom_jobs(jobs, instance_name=instance_name)


def strategy_from_defaults(defaults: Dict[str, Any]) -> SchedulingStrategy:
    return SchedulingStrategy.from_dict(defaults or {})


def sorted_jobs_like_builder(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        jobs,
        key=lambda x: int((x.get("priority") if isinstance(x, dict) else 10) or 10),
        reverse=True,
    )


def gantt_job_names(gantt: List[Dict[str, Any]], job_name_map: Dict[int, str]) -> List[Dict[str, Any]]:
    out = []
    for item in gantt or []:
        row = dict(item)
        jid = row.get("job_id")
        if jid in job_name_map:
            row["job_name"] = job_name_map[jid]
        out.append(row)
    return out


def is_photo_task(task: Dict[str, Any]) -> bool:
    area = str(task.get("process_area") or "").lower()
    if area in ("photo", "photolithography"):
        return True
    return "photo" in str(task.get("name") or "").lower()
