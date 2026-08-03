"""从 planning jobs 解析/构建 JobShopProblem。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from metaforge.utils.problem_builder import (
    apply_downtime_blocks,
    build_problem_from_custom_jobs,
)


def _jobs_have_tasks(jobs: Iterable[Any]) -> bool:
    for job in jobs or []:
        if isinstance(job, dict) and (job.get("tasks") or job.get("operations")):
            return True
        if getattr(job, "tasks", None):
            return True
    return False


def _normalize_jobs_for_builder(jobs: Iterable[Any]) -> List[Any]:
    """Align planning payloads that use operations[] with problem_builder tasks[]."""
    out: List[Any] = []
    for job in jobs or []:
        if not isinstance(job, dict):
            out.append(job)
            continue
        item = dict(job)
        if not item.get("tasks") and item.get("operations"):
            tasks = []
            for op in item.get("operations") or []:
                if not isinstance(op, dict):
                    continue
                tasks.append(
                    {
                        "name": op.get("name") or op.get("operation_id"),
                        "machine_id": op.get("machine_id", op.get("machine")),
                        "machine_options": op.get("machine_options") or op.get("eligible_machines"),
                        "duration": op.get("duration") or op.get("time") or op.get("standard_duration"),
                        "setup_time": op.get("setup_time"),
                        "unit_time": op.get("unit_time"),
                    }
                )
            item["tasks"] = tasks
        out.append(item)
    return out


def build_job_aliases(custom_jobs: List[Any], job_name_map: Dict[int, str]) -> Dict[str, List[str]]:
    """Map problem job index -> alias keys used by strategy constraints / evaluator."""
    aliases: Dict[str, List[str]] = {}
    # rebuild sorted order same as problem_builder
    sorted_jobs = sorted(
        custom_jobs,
        key=lambda x: int((x.get("priority") if isinstance(x, dict) else getattr(x, "priority", 10)) or 10),
        reverse=True,
    )
    for idx, job in enumerate(sorted_jobs):
        keys = {str(idx)}
        name = job_name_map.get(idx)
        if name:
            keys.add(str(name))
        if isinstance(job, dict):
            for k in ("job_id", "id", "name"):
                if job.get(k) is not None and job.get(k) != "":
                    keys.add(str(job[k]))
        aliases[str(idx)] = sorted(keys)
    return aliases


def resolve_planning_problem(
    jobs: Any = None,
    *,
    problem: Any = None,
    resource_config: Optional[Dict[str, Any]] = None,
    instance_name: str = "Planning Run",
) -> Tuple[Any, Dict[str, Any]]:
    """
    Return (problem, meta).
    meta may include job_aliases, warnings, built_from_jobs.
    """
    meta: Dict[str, Any] = {"built_from_jobs": False, "warnings": []}

    if problem is not None:
        if resource_config:
            apply_downtime_blocks(problem, resource_config)
        return problem, meta

    job_list = list(jobs or [])
    if not job_list:
        meta["warnings"].append("no jobs provided; cannot build problem")
        return None, meta

    normalized = _normalize_jobs_for_builder(job_list)
    if not _jobs_have_tasks(normalized):
        meta["warnings"].append("jobs have no tasks/operations; cannot build problem")
        return None, meta

    try:
        built, name_map, _prio = build_problem_from_custom_jobs(
            normalized, instance_name=instance_name
        )
    except Exception as exc:  # noqa: BLE001
        meta["warnings"].append(f"failed to build problem: {exc}")
        return None, meta

    if resource_config:
        apply_downtime_blocks(built, resource_config)

    meta["built_from_jobs"] = True
    meta["job_aliases"] = build_job_aliases(normalized, name_map)
    meta["job_name_map"] = {str(k): v for k, v in name_map.items()}
    return built, meta


def enrich_completion_aliases(
    completion_by_job: Dict[str, float],
    job_aliases: Optional[Dict[str, List[str]]],
) -> Dict[str, float]:
    if not job_aliases:
        return dict(completion_by_job)
    out = dict(completion_by_job)
    for idx, aliases in job_aliases.items():
        value = None
        for key in [idx, *aliases]:
            if key in completion_by_job:
                value = completion_by_job[key]
                break
        if value is None:
            continue
        for key in aliases:
            out[key] = float(value)
    return out
