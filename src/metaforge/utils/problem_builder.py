"""从 API 工单数据构建 JobShopProblem（与 tests/main JobData 字段对齐）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from metaforge.problems.jobshop import Job, JobShopProblem, Task


def refine_auto_due_dates(problem: JobShopProblem) -> None:
    """
    未显式填写交期的工单：用「本单工时 + 车间排队裕量」估算承诺交期。
    避免仅用 2.5×本单工时导致与真实完工差距过大、承诺评估全员高风险。
    """
    jobs = problem.jobs
    if not jobs:
        return
    n = len(jobs)
    m = max(int(getattr(problem, "num_machines", 1) or 1), 1)
    total_work = sum(sum(t.duration for t in j.tasks) for j in jobs)
    shop_floor = total_work / m

    for j in jobs:
        if getattr(j, "due_date_explicit", False):
            continue
        proc = sum(t.duration for t in j.tasks)
        queue_slack = shop_floor * (0.35 + 0.12 * min(n, 20))
        j.due_date = float(j.arrival_time) + proc + queue_slack


def resolve_task_duration(
    task: Any,
    *,
    job_quantity: Optional[int] = None,
) -> int:
    """若提供 setup_time + unit_time + 数量，则 duration = setup + unit * qty。"""
    qty = getattr(task, "quantity", None)
    if qty is None and isinstance(task, dict):
        qty = task.get("quantity")
    if qty is None:
        qty = job_quantity

    setup = getattr(task, "setup_time", None)
    unit = getattr(task, "unit_time", None)
    duration = getattr(task, "duration", 1)
    if isinstance(task, dict):
        setup = task.get("setup_time", setup)
        unit = task.get("unit_time", unit)
        duration = task.get("duration", duration)

    if setup is not None and unit is not None and qty is not None and int(qty) > 0:
        return max(1, int(round(float(setup) + float(unit) * int(qty))))
    return max(1, int(duration or 1))


def _task_list(job: Any) -> List[Any]:
    tasks = getattr(job, "tasks", None)
    if tasks is None and isinstance(job, dict):
        tasks = job.get("tasks") or []
    return list(tasks or [])


def _job_field(job: Any, key: str, default=None):
    if isinstance(job, dict):
        return job.get(key, default)
    return getattr(job, key, default)


def build_problem_from_custom_jobs(
    custom_jobs: List[Any],
    *,
    instance_name: str = "Custom Plan",
) -> Tuple[JobShopProblem, Dict[int, str], Dict[int, int]]:
    jobs: List[Job] = []
    job_name_map: Dict[int, str] = {}
    job_priority_map: Dict[int, int] = {}

    sorted_jobs = sorted(
        custom_jobs,
        key=lambda x: int(_job_field(x, "priority", 10) or 10),
        reverse=True,
    )

    for i, job_data in enumerate(sorted_jobs):
        job_name_map[i] = str(_job_field(job_data, "name", f"Job-{i}"))
        job_priority_map[i] = int(_job_field(job_data, "priority", 10) or 10)

    for j_idx, job_data in enumerate(sorted_jobs):
        tasks = []
        job_name = str(_job_field(job_data, "name", f"Job-{j_idx}"))
        job_qty = _job_field(job_data, "quantity")

        for op_id, t in enumerate(_task_list(job_data)):
            op_name = _job_field(t, "name") or f"{job_name}-Op{op_id + 1}"
            options = list(_job_field(t, "machine_options") or [])
            mid = _job_field(t, "machine_id")
            if mid is not None and mid not in options:
                options.insert(0, int(mid))
            if not options:
                options = [0]
            proc_duration = resolve_task_duration(t, job_quantity=job_qty)
            tasks.append(
                Task(
                    machine_id=int(mid if mid is not None else options[0]),
                    machine_options=options,
                    machine_group=_job_field(t, "machine_group"),
                    duration=proc_duration,
                    id=op_id,
                    name=str(op_name),
                )
            )

        priority = int(_job_field(job_data, "priority", 10) or 10)
        job_kwargs: Dict[str, Any] = {"tasks": tasks, "id": j_idx, "priority": priority}
        due = _job_field(job_data, "due_date")
        if due is not None:
            job_kwargs["due_date"] = float(due)
        arrival = _job_field(job_data, "material_arrival")
        if arrival is not None:
            job_kwargs["arrival_time"] = float(arrival)
        try:
            jobs.append(Job(**job_kwargs))
        except TypeError:
            jobs.append(Job(tasks=tasks, id=j_idx))

    problem = JobShopProblem(jobs, instance_name=instance_name)
    refine_auto_due_dates(problem)
    return problem, job_name_map, job_priority_map


def apply_downtime_blocks(problem: JobShopProblem, resource_config: Optional[Dict[str, Any]]) -> None:
    if not resource_config:
        return
    for block in resource_config.get("downtime_blocks") or []:
        try:
            mid = int(block["machine_id"])
            start = float(block["start"])
            end = float(block["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if mid < 0 or mid >= problem.num_machines or end <= start:
            continue
        problem.machines[mid].maintenance.append(
            {
                "start": start,
                "end": end,
                "label": block.get("label", "downtime"),
            }
        )
