"""事件重排服务（同步，供 events Tool 与 REST 复用）。"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from metaforge.problems.jobshop import Job, JobShopProblem
from metaforge.utils.compare_solvers import compare_solvers
from metaforge.utils.delivery_prediction import compute_delivery_predictions
from metaforge.utils.event_helpers import (
    attach_delivery_predictions,
    build_commitment_changes,
    build_delay_impact_report,
    job_completion_map,
    merge_repaired_schedule,
)
from metaforge.utils.event_mutations import (
    apply_material_delay,
    apply_order_cancel,
    apply_priority_changes,
    apply_quantity_changes,
    merge_downtime_blocks,
)
from metaforge.utils.gantt_propagate import propagate_breakdown_on_gantt
from metaforge.utils.problem_builder import apply_downtime_blocks, build_problem_from_custom_jobs
from metaforge.utils.gantt_insert_defer import defer_insert_to_tail_gantt
from metaforge.utils.due_date_impact import build_due_date_impact_report
from metaforge.utils.insert_impact import build_insert_impact_report
from metaforge.utils.recovery_impact import build_recovery_impact_report
from metaforge.utils.solver_registry import resolve_solver_id, try_resolve_solver_id


def _ok_payload(results: Dict[str, Any], impact_report: Dict[str, Any], **extra_data) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "results": results,
        "impact_report": impact_report,
        "impact_gantt": {
            "r0": (impact_report or {}).get("r0_gantt"),
            "r1": (impact_report or {}).get("r1_gantt"),
            "r2": (impact_report or {}).get("r2_gantt"),
        },
    }
    data.update(extra_data)
    return {"status": "success", "data": data}


def _job_to_dict(job: Any) -> Dict[str, Any]:
    if isinstance(job, dict):
        return copy.deepcopy(job)
    if hasattr(job, "model_dump"):
        return job.model_dump()
    return dict(job)


def _align_machine_breakdown_times(
    params: Dict[str, Any], exec_doc: Dict[str, Any]
) -> Dict[str, Any]:
    """MES 执行中：LLM/默认常把故障时刻写成 0，应对齐到当前仿真时刻（如 sim=10h）。"""
    p = dict(params)
    if exec_doc.get("status") not in ("running", "paused"):
        return p
    try:
        sim = float(exec_doc.get("sim_time") if exec_doc.get("sim_time") is not None else -1)
    except (TypeError, ValueError):
        return p
    if sim <= 1e-9:
        return p

    def _bump_zero(key: str) -> None:
        val = p.get(key)
        if val is None:
            p[key] = sim
            return
        try:
            fv = float(val)
        except (TypeError, ValueError):
            return
        if fv <= 1e-9:
            p[key] = sim

    _bump_zero("breakdown_start")
    _bump_zero("freeze_time")
    if p.get("freeze_time") is None:
        p["freeze_time"] = sim
    if p.get("breakdown_start") is None:
        p["breakdown_start"] = sim
    return p


def _apply_execution_context(
    envelope: Dict[str, Any],
    base_jobs: List[Any],
    kw: Dict[str, Any],
    params: Dict[str, Any],
) -> Tuple[List[Any], Optional[List[Dict[str, Any]]], Optional[str], Dict[str, Any], Dict[str, Any]]:
    exec_doc = envelope.get("production_execution") or {}
    opts = envelope.get("reschedule_options") or {}
    bl_gantt = opts.get("baseline_gantt") or exec_doc.get("baseline_gantt")
    bl_solver = opts.get("baseline_solver") or exec_doc.get("baseline_solver")
    if bl_solver:
        bl_solver = try_resolve_solver_id(str(bl_solver), default=str(bl_solver).strip())
        opts["baseline_solver"] = bl_solver
    jobs = exec_doc.get("jobs_snapshot") or base_jobs
    if bl_solver and not kw.get("solvers"):
        kw["solvers"] = [bl_solver]
    if params.get("freeze_time") is None and exec_doc.get("sim_time") is not None:
        params["freeze_time"] = float(exec_doc["sim_time"])
    return jobs, bl_gantt, bl_solver, kw, params


def run_global_reschedule(
    base_jobs: List[Any],
    *,
    mutate_fn,
    event_type: str,
    event_meta: Dict[str, Any],
    solvers: Optional[List[str]] = None,
    weights: Optional[Dict[str, float]] = None,
    resource_config: Optional[Dict[str, Any]] = None,
    random_seed: Optional[int] = None,
    baseline_gantt: Optional[List[Dict[str, Any]]] = None,
    baseline_solver: Optional[str] = None,
) -> Dict[str, Any]:
    solvers = solvers or ["ts", "spt"]
    base_problem, base_name_map, _ = build_problem_from_custom_jobs(
        base_jobs, instance_name="Event Base"
    )
    apply_downtime_blocks(base_problem, resource_config)

    if baseline_gantt:
        baseline_solver = str(baseline_solver or solvers[0])
        baseline_gantt_data = copy.deepcopy(baseline_gantt)
        baseline = {baseline_solver: {"gantt_data": baseline_gantt_data, "metrics": {}}}
    else:
        baseline = compare_solvers(
            solvers[:1],
            base_problem,
            weights=weights,
            resource_config=resource_config,
            random_seed=random_seed,
        )
        baseline_solver = next(iter(baseline.keys()))
        baseline_gantt_data = baseline[baseline_solver].get("gantt_data", [])

    baseline_completion = job_completion_map(baseline_gantt_data)

    updated_jobs = mutate_fn(copy.deepcopy(base_jobs))
    new_problem, new_name_map, _ = build_problem_from_custom_jobs(
        updated_jobs, instance_name="Event Updated"
    )
    apply_downtime_blocks(new_problem, resource_config)
    results = compare_solvers(
        solvers,
        new_problem,
        weights=weights,
        resource_config=resource_config,
        random_seed=random_seed,
    )
    attach_delivery_predictions(results, new_problem, new_name_map)

    new_solver = next(iter(results.keys()))
    new_gantt = results[new_solver].get("gantt_data", [])
    new_completion = job_completion_map(new_gantt)

    baseline_cv = (baseline.get(baseline_solver, {}).get("metrics") or {}).get("machine_busy_cv")
    before_pred = compute_delivery_predictions(
        baseline_gantt_data, base_problem, job_name_map=base_name_map, machine_busy_cv=baseline_cv
    )
    new_cv = (results[new_solver].get("metrics") or {}).get("machine_busy_cv")
    after_pred = compute_delivery_predictions(
        new_gantt, new_problem, job_name_map=new_name_map, machine_busy_cv=new_cv
    )

    impact = build_delay_impact_report(
        baseline_completion=baseline_completion,
        new_completion=new_completion,
        job_name_map=base_name_map,
        before_pred=before_pred,
        after_pred=after_pred,
        baseline_solver=baseline_solver,
        rescheduled_solver=new_solver,
        extra={"event_type": event_type, **event_meta},
    )
    return _ok_payload(results, impact)


def run_due_date_change(
    base_jobs: List[Any],
    due_date_changes: List[Dict[str, Any]],
    **kwargs,
) -> Dict[str, Any]:
    solvers = kwargs.get("solvers") or ["ts", "edd"]
    weights = kwargs.get("weights")
    resource_config = kwargs.get("resource_config")
    random_seed = kwargs.get("random_seed")
    baseline_gantt = kwargs.get("baseline_gantt")
    baseline_solver = kwargs.get("baseline_solver")

    changes_list = [
        {"job_name": str(c["job_name"]), "new_due_date": float(c["new_due_date"])}
        for c in due_date_changes
    ]
    cmap = {c["job_name"]: c["new_due_date"] for c in changes_list}

    def mutate(jobs):
        for job in jobs:
            name = job.name if hasattr(job, "name") else job.get("name")
            if name in cmap:
                if isinstance(job, dict):
                    job["due_date"] = cmap[name]
                else:
                    job.due_date = cmap[name]
        return jobs

    updated_jobs = mutate(copy.deepcopy(base_jobs))

    base_problem, base_name_map, _ = build_problem_from_custom_jobs(
        base_jobs, instance_name="Due Date Base"
    )
    apply_downtime_blocks(base_problem, resource_config)

    if baseline_gantt:
        baseline_solver = str(baseline_solver or solvers[0])
        baseline_gantt_data = copy.deepcopy(baseline_gantt)
        baseline = {baseline_solver: {"gantt_data": baseline_gantt_data, "metrics": {}}}
    else:
        baseline = compare_solvers(
            solvers[:1],
            base_problem,
            weights=weights,
            resource_config=resource_config,
            random_seed=random_seed,
        )
        baseline_solver = next(iter(baseline.keys()))
        baseline_gantt_data = baseline[baseline_solver].get("gantt_data", [])

    r0_gantt = copy.deepcopy(baseline_gantt_data)
    r1_gantt = copy.deepcopy(baseline_gantt_data)

    new_problem, new_name_map, _ = build_problem_from_custom_jobs(
        updated_jobs, instance_name="Due Date Updated"
    )
    apply_downtime_blocks(new_problem, resource_config)
    results = compare_solvers(
        solvers,
        new_problem,
        weights=weights,
        resource_config=resource_config,
        random_seed=random_seed,
    )
    attach_delivery_predictions(results, new_problem, new_name_map)

    new_solver = next(iter(results.keys()))
    new_gantt = results[new_solver].get("gantt_data", [])

    impact = build_due_date_impact_report(
        r0_gantt=r0_gantt,
        r1_gantt=r1_gantt,
        r2_gantt=new_gantt,
        base_problem=base_problem,
        new_problem=new_problem,
        job_name_map=new_name_map,
        due_date_changes=changes_list,
        baseline_solver=baseline_solver,
        rescheduled_solver=new_solver,
        resource_config=resource_config,
    )

    baseline_cv = (baseline.get(baseline_solver, {}).get("metrics") or {}).get("machine_busy_cv")
    before_pred = compute_delivery_predictions(
        r1_gantt, new_problem, job_name_map=new_name_map, machine_busy_cv=baseline_cv
    )
    new_cv = (results[new_solver].get("metrics") or {}).get("machine_busy_cv")
    after_pred = compute_delivery_predictions(
        new_gantt, new_problem, job_name_map=new_name_map, machine_busy_cv=new_cv
    )
    impact["commitment_changes"] = build_commitment_changes(before_pred, after_pred)

    return _ok_payload(
        results,
        impact,
        updated_jobs=[_job_to_dict(j) for j in updated_jobs],
    )


def run_planned_downtime(
    base_jobs: List[Any],
    downtime_blocks: List[Dict[str, Any]],
    **kwargs,
) -> Dict[str, Any]:
    solvers = kwargs.get("solvers") or ["ts", "spt"]
    weights = kwargs.get("weights")
    random_seed = kwargs.get("random_seed")
    old_cfg = kwargs.get("resource_config")
    new_cfg = merge_downtime_blocks(old_cfg, downtime_blocks)

    base_problem, base_name_map, _ = build_problem_from_custom_jobs(base_jobs, instance_name="Downtime Base")
    apply_downtime_blocks(base_problem, old_cfg)
    baseline = compare_solvers(solvers[:1], base_problem, weights=weights, resource_config=old_cfg, random_seed=random_seed)
    baseline_solver = next(iter(baseline.keys()))
    baseline_gantt = baseline[baseline_solver].get("gantt_data", [])
    baseline_completion = job_completion_map(baseline_gantt)

    new_problem, new_name_map, _ = build_problem_from_custom_jobs(base_jobs, instance_name="Downtime Updated")
    apply_downtime_blocks(new_problem, new_cfg)
    results = compare_solvers(solvers, new_problem, weights=weights, resource_config=new_cfg, random_seed=random_seed)
    attach_delivery_predictions(results, new_problem, new_name_map)

    new_solver = next(iter(results.keys()))
    new_gantt = results[new_solver].get("gantt_data", [])
    new_completion = job_completion_map(new_gantt)

    baseline_cv = (baseline.get(baseline_solver, {}).get("metrics") or {}).get("machine_busy_cv")
    before_pred = compute_delivery_predictions(baseline_gantt, base_problem, job_name_map=base_name_map, machine_busy_cv=baseline_cv)
    new_cv = (results[new_solver].get("metrics") or {}).get("machine_busy_cv")
    after_pred = compute_delivery_predictions(new_gantt, new_problem, job_name_map=new_name_map, machine_busy_cv=new_cv)

    impact = build_delay_impact_report(
        baseline_completion=baseline_completion,
        new_completion=new_completion,
        job_name_map=base_name_map,
        before_pred=before_pred,
        after_pred=after_pred,
        baseline_solver=baseline_solver,
        rescheduled_solver=new_solver,
        extra={"event_type": "planned_downtime", "downtime_blocks": downtime_blocks},
    )
    return _ok_payload(results, impact)


def run_priority_change(base_jobs: List[Any], changes: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    return run_global_reschedule(
        base_jobs,
        mutate_fn=lambda j: apply_priority_changes(j, changes),
        event_type="priority_change",
        event_meta={"changes": changes},
        **kwargs,
    )


def run_order_cancel(base_jobs: List[Any], job_names: List[str], **kwargs) -> Dict[str, Any]:
    return run_global_reschedule(
        base_jobs,
        mutate_fn=lambda j: apply_order_cancel(j, job_names),
        event_type="order_cancel",
        event_meta={"cancelled": job_names},
        **kwargs,
    )


def run_material_delay(
    base_jobs: List[Any],
    job_name: str,
    delay_hours: float,
    **kwargs,
) -> Dict[str, Any]:
    return run_global_reschedule(
        base_jobs,
        mutate_fn=lambda j: apply_material_delay(j, job_name, delay_hours),
        event_type="material_delay",
        event_meta={"job_name": job_name, "delay_hours": delay_hours},
        **kwargs,
    )


def run_quantity_change(base_jobs: List[Any], changes: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    return run_global_reschedule(
        base_jobs,
        mutate_fn=lambda j: apply_quantity_changes(j, changes),
        event_type="quantity_change",
        event_meta={"changes": changes},
        **kwargs,
    )


def run_insert_order(
    base_jobs: List[Any],
    insert_job: Any,
    *,
    freeze_time: float = 0.0,
    mode: str = "local_repair",
    baseline_gantt: Optional[List[Dict[str, Any]]] = None,
    baseline_solver: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    solvers = kwargs.get("solvers") or ["ts", "spt"]
    weights = kwargs.get("weights")
    resource_config = kwargs.get("resource_config")
    random_seed = kwargs.get("random_seed")
    freeze_time = max(0.0, float(freeze_time or 0.0))

    base_problem, base_name_map, base_priority_map = build_problem_from_custom_jobs(
        base_jobs, instance_name="Insert Base"
    )
    apply_downtime_blocks(base_problem, resource_config)

    if baseline_gantt:
        baseline_solver = str(baseline_solver or solvers[0])
        baseline_gantt = copy.deepcopy(baseline_gantt)
        baseline = {baseline_solver: {"gantt_data": baseline_gantt, "metrics": {}}}
    else:
        baseline = compare_solvers(
            solvers[:1], base_problem, weights=weights, resource_config=resource_config, random_seed=random_seed
        )
        baseline_solver = next(iter(baseline.keys()))
        baseline_gantt = baseline[baseline_solver].get("gantt_data", [])

    baseline_completion = job_completion_map(baseline_gantt)
    repair_solvers = [baseline_solver] if baseline_solver else solvers

    if mode == "global":
        merged_jobs = list(base_jobs) + [insert_job]
        merged_problem, merged_name_map, merged_priority_map = build_problem_from_custom_jobs(
            merged_jobs, instance_name="Insert Global"
        )
        apply_downtime_blocks(merged_problem, resource_config)
        results = compare_solvers(
            repair_solvers if baseline_solver else solvers,
            merged_problem,
            weights=weights,
            resource_config=resource_config,
            random_seed=random_seed,
        )
        full_problem = merged_problem
        display_name_map = merged_name_map
        for res in results.values():
            for item in res.get("gantt_data", []):
                jid = int(item["job_id"])
                if jid in display_name_map:
                    item["job_name"] = display_name_map[jid]
    else:
        frozen_ops = [op for op in baseline_gantt if float(op.get("start", 0)) < freeze_time]
        machine_ready = [0.0] * base_problem.num_machines
        completed_count = [0] * base_problem.num_jobs
        for op in frozen_ops:
            machine_ready[int(op["machine_id"])] = max(machine_ready[int(op["machine_id"])], float(op["end"]))
            completed_count[int(op["job_id"])] += 1

        residual_jobs: List[Job] = []
        residual_name_map: Dict[int, str] = {}
        residual_priority_map: Dict[int, int] = {}
        residual_index_to_job_id: Dict[int, int] = {}

        for jid, base_job in enumerate(base_problem.jobs):
            remain = base_job.tasks[completed_count[jid] :]
            if not remain:
                continue
            ready = max(
                freeze_time,
                max([float(op["end"]) for op in frozen_ops if int(op["job_id"]) == jid], default=0.0),
            )
            residual_jobs.append(
                Job(
                    tasks=remain,
                    id=jid,
                    arrival_time=ready,
                    priority=getattr(base_job, "priority", 10),
                    due_date=getattr(base_job, "due_date", None),
                )
            )
            residual_name_map[jid] = base_name_map.get(jid, f"Job-{jid}")
            residual_priority_map[jid] = getattr(base_job, "priority", 10)
            residual_index_to_job_id[len(residual_jobs) - 1] = jid

        ins_prob, _, _ = build_problem_from_custom_jobs([insert_job], instance_name="insert")
        insert_job_obj = ins_prob.jobs[0]
        insert_idx = base_problem.num_jobs
        insert_job_obj.id = insert_idx
        insert_job_obj.arrival_time = freeze_time
        residual_jobs.append(insert_job_obj)
        residual_index_to_job_id[len(residual_jobs) - 1] = insert_idx
        ins_name = insert_job.name if hasattr(insert_job, "name") else insert_job.get("name", "Insert")
        residual_name_map[insert_idx] = ins_name
        residual_priority_map[insert_idx] = getattr(insert_job, "priority", 10)

        residual_problem = JobShopProblem(
            residual_jobs,
            instance_name="Insert Local",
            initial_machine_ready=machine_ready,
        )
        apply_downtime_blocks(residual_problem, resource_config)
        results = compare_solvers(
            repair_solvers, residual_problem, weights=weights, resource_config=resource_config, random_seed=random_seed
        )
        for res in results.values():
            merged = merge_repaired_schedule(frozen_ops, res.get("gantt_data", []), residual_index_to_job_id)
            res["gantt_data"] = merged

        full_jobs = list(base_jobs) + [insert_job]
        full_problem, full_name_map, _ = build_problem_from_custom_jobs(full_jobs, instance_name="Insert Full")
        display_name_map = {**base_name_map, **residual_name_map}
        for res in results.values():
            for item in res.get("gantt_data", []):
                jid = int(item["job_id"])
                if jid in display_name_map:
                    item["job_name"] = display_name_map[jid]

    attach_delivery_predictions(results, full_problem, display_name_map)
    new_solver = next(iter(results.keys()))
    new_gantt = results[new_solver].get("gantt_data", [])
    insert_job_id = base_problem.num_jobs
    ins_name = insert_job.name if hasattr(insert_job, "name") else insert_job.get("name", "Insert")
    ins_priority = int(
        insert_job.priority if hasattr(insert_job, "priority") else insert_job.get("priority", 100) or 100
    )
    if hasattr(insert_job, "tasks"):
        ins_tasks = [
            {
                "name": getattr(t, "name", f"Op-{i + 1}"),
                "machine_id": getattr(t, "machine_id", None),
                "machine_options": list(getattr(t, "machine_options", None) or []),
                "duration": getattr(t, "duration", 1),
            }
            for i, t in enumerate(insert_job.tasks)
        ]
    else:
        ins_tasks = list((insert_job.get("tasks") or []))
    insert_job_snapshot = {"name": ins_name, "priority": ins_priority, "tasks": ins_tasks, "job_id": insert_job_id}

    r1_gantt = defer_insert_to_tail_gantt(
        baseline_gantt,
        insert_job,
        insert_job_id,
        freeze_time=freeze_time,
        insert_priority=ins_priority,
    )
    for op in r1_gantt:
        jid = int(op.get("job_id", -1))
        if jid == insert_job_id:
            op["job_name"] = ins_name
            op["priority"] = ins_priority

    impact = build_insert_impact_report(
        r0_gantt=baseline_gantt,
        r1_gantt=r1_gantt,
        r2_gantt=new_gantt,
        problem=full_problem,
        job_name_map=display_name_map,
        insert_job_id=insert_job_id,
        insert_job_name=ins_name,
        insert_job_snapshot=insert_job_snapshot,
        baseline_solver=baseline_solver,
        rescheduled_solver=new_solver,
        freeze_time=freeze_time,
        mode=mode,
        resource_config=resource_config,
    )

    baseline_cv = (baseline.get(baseline_solver, {}).get("metrics") or {}).get("machine_busy_cv")
    before_pred = compute_delivery_predictions(
        r1_gantt, full_problem, job_name_map=display_name_map, machine_busy_cv=baseline_cv
    )
    new_cv = (results[new_solver].get("metrics") or {}).get("machine_busy_cv")
    after_pred = compute_delivery_predictions(
        new_gantt, full_problem, job_name_map=display_name_map, machine_busy_cv=new_cv
    )
    impact["commitment_changes"] = build_commitment_changes(before_pred, after_pred)
    updated_jobs = [_job_to_dict(j) for j in base_jobs] + [_job_to_dict(insert_job)]
    return _ok_payload(results, impact, updated_jobs=updated_jobs)


def run_machine_breakdown(
    base_jobs: List[Any],
    machine_id: int,
    breakdown_start: float,
    breakdown_duration: float,
    freeze_time: Optional[float] = None,
    *,
    baseline_gantt: Optional[List[Dict[str, Any]]] = None,
    baseline_solver: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    solvers_in = kwargs.get("solvers") or []
    weights = kwargs.get("weights")
    resource_config = kwargs.get("resource_config")
    random_seed = kwargs.get("random_seed")
    freeze_time = max(0.0, float(freeze_time if freeze_time is not None else breakdown_start))
    breakdown_start = float(breakdown_start)
    breakdown_end = breakdown_start + float(breakdown_duration)
    machine_id = int(machine_id)

    base_problem, base_name_map, base_priority_map = build_problem_from_custom_jobs(
        base_jobs, instance_name="Breakdown Base"
    )
    apply_downtime_blocks(base_problem, resource_config)

    if baseline_gantt:
        r0_gantt = [copy.deepcopy(op) for op in baseline_gantt]
        raw_sid = str(baseline_solver or (solvers_in[0] if solvers_in else "ts"))
        solver_id = try_resolve_solver_id(raw_sid, default=raw_sid.strip()) or raw_sid
    else:
        fallback = solvers_in or ["ts"]
        baseline = compare_solvers(
            fallback[:1],
            base_problem,
            weights=weights,
            resource_config=resource_config,
            random_seed=random_seed,
        )
        solver_id = next(iter(baseline.keys()))
        r0_gantt = baseline[solver_id].get("gantt_data", [])

    r1_gantt = propagate_breakdown_on_gantt(
        r0_gantt,
        machine_id=machine_id,
        breakdown_start=breakdown_start,
        breakdown_duration=breakdown_duration,
    )

    frozen_ops = [op for op in r0_gantt if float(op.get("start", 0)) < freeze_time]
    machine_ready = [0.0] * base_problem.num_machines
    completed_count = [0] * base_problem.num_jobs
    for op in frozen_ops:
        machine_ready[int(op["machine_id"])] = max(machine_ready[int(op["machine_id"])], float(op["end"]))
        completed_count[int(op["job_id"])] += 1
    if 0 <= machine_id < len(machine_ready):
        machine_ready[machine_id] = max(machine_ready[machine_id], breakdown_end)

    residual_jobs: List[Job] = []
    residual_index_to_job_id: Dict[int, int] = {}
    residual_name_map: Dict[int, str] = {}

    for jid, base_job in enumerate(base_problem.jobs):
        remain = base_job.tasks[completed_count[jid] :]
        if not remain:
            continue
        ready = max(
            freeze_time,
            max([float(op["end"]) for op in frozen_ops if int(op["job_id"]) == jid], default=0.0),
        )
        residual_jobs.append(
            Job(
                tasks=remain,
                id=jid,
                arrival_time=ready,
                priority=getattr(base_job, "priority", 10),
                due_date=getattr(base_job, "due_date", None),
            )
        )
        residual_name_map[jid] = base_name_map.get(jid, f"Job-{jid}")
        residual_index_to_job_id[len(residual_jobs) - 1] = jid

    if not residual_jobs:
        return {"error": "no residual work to reschedule after freeze"}

    residual_problem = JobShopProblem(
        residual_jobs,
        instance_name="Breakdown Repair",
        initial_machine_ready=machine_ready,
    )
    apply_downtime_blocks(residual_problem, resource_config)
    try:
        solver_id = resolve_solver_id(solver_id)
    except ValueError:
        pass

    results = compare_solvers(
        [solver_id],
        residual_problem,
        weights=weights,
        resource_config=resource_config,
        random_seed=random_seed,
    )

    for res in results.values():
        merged = merge_repaired_schedule(
            frozen_ops, res.get("gantt_data", []), residual_index_to_job_id
        )
        for item in merged:
            jid = int(item["job_id"])
            if jid in residual_name_map:
                item["job_name"] = residual_name_map[jid]
            elif jid in base_name_map:
                item["job_name"] = base_name_map[jid]
        res["gantt_data"] = merged

    new_solver = solver_id
    new_gantt = results[new_solver].get("gantt_data", [])

    impact = build_recovery_impact_report(
        r0_gantt=r0_gantt,
        r1_gantt=r1_gantt,
        r2_gantt=new_gantt,
        problem=base_problem,
        job_name_map=base_name_map,
        baseline_solver=solver_id,
        rescheduled_solver=new_solver,
        machine_id=machine_id,
        breakdown_start=float(breakdown_start),
        breakdown_end=breakdown_end,
        freeze_time=freeze_time,
        resource_config=resource_config,
    )
    attach_delivery_predictions(results, base_problem, base_name_map)
    if baseline_gantt:
        baseline_cv = None
    else:
        _bl_key = next(iter(baseline.keys()))
        baseline_cv = (baseline.get(_bl_key, {}).get("metrics") or {}).get("machine_busy_cv")
    new_cv = (results.get(new_solver, {}).get("metrics") or {}).get("machine_busy_cv")
    before_pred = compute_delivery_predictions(
        r1_gantt,
        base_problem,
        job_name_map=base_name_map,
        machine_busy_cv=baseline_cv,
    )
    after_pred = compute_delivery_predictions(
        new_gantt,
        base_problem,
        job_name_map=base_name_map,
        machine_busy_cv=new_cv,
    )
    impact["commitment_changes"] = build_commitment_changes(before_pred, after_pred)
    return _ok_payload(results, impact)


def dispatch_event_reschedule(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """根据 event_envelope 分发重排。"""
    event_type = envelope.get("event_type")
    base_jobs = envelope.get("base_jobs") or []
    opts = envelope.get("reschedule_options") or {}
    params = envelope.get("params") or {}
    kw = {
        "solvers": opts.get("solvers"),
        "weights": opts.get("weights"),
        "resource_config": opts.get("resource_config"),
        "random_seed": opts.get("random_seed"),
    }

    if not base_jobs:
        return {
            "error": "缺少基准工单：请先在排程中心保存计划，或在助手/报表中打开时已自动载入的工单"
        }

    if event_type == "insert_order":
        insert_job = params.get("insert_job")
        if insert_job is None:
            return {"error": "insert_job required"}
        jobs, bl_gantt, bl_solver, kw, params = _apply_execution_context(
            envelope, base_jobs, kw, params
        )
        return run_insert_order(
            jobs,
            insert_job,
            freeze_time=float(params.get("freeze_time", opts.get("freeze_time", 0))),
            mode=str(params.get("mode", opts.get("mode", "local_repair"))),
            baseline_gantt=bl_gantt,
            baseline_solver=bl_solver,
            **kw,
        )
    if event_type == "machine_breakdown":
        exec_doc = envelope.get("production_execution") or {}
        bl_gantt = opts.get("baseline_gantt") or exec_doc.get("baseline_gantt")
        bl_solver = opts.get("baseline_solver") or exec_doc.get("baseline_solver")
        if exec_doc.get("jobs_snapshot"):
            base_jobs = exec_doc["jobs_snapshot"]
        if bl_solver and not kw.get("solvers"):
            kw["solvers"] = [bl_solver]
        params = _align_machine_breakdown_times(params, exec_doc)
        if params.get("breakdown_start") is None and exec_doc.get("sim_time") is not None:
            params["breakdown_start"] = float(exec_doc["sim_time"])
        if params.get("freeze_time") is None and exec_doc.get("sim_time") is not None:
            params["freeze_time"] = float(exec_doc["sim_time"])
        return run_machine_breakdown(
            base_jobs,
            machine_id=int(params["machine_id"]),
            breakdown_start=float(params["breakdown_start"]),
            breakdown_duration=float(params["breakdown_duration"]),
            freeze_time=params.get("freeze_time"),
            baseline_gantt=bl_gantt,
            baseline_solver=bl_solver,
            **kw,
        )
    if event_type == "due_date_change":
        jobs, bl_gantt, bl_solver, kw, _params = _apply_execution_context(
            envelope, base_jobs, kw, params
        )
        return run_due_date_change(
            jobs,
            params.get("due_date_changes", []),
            baseline_gantt=bl_gantt,
            baseline_solver=bl_solver,
            **kw,
        )
    if event_type == "planned_downtime":
        return run_planned_downtime(base_jobs, params.get("downtime_blocks", []), **kw)
    if event_type == "material_delay":
        return run_material_delay(
            base_jobs,
            str(params.get("job_name", "")),
            float(params.get("delay_hours", 0)),
            **kw,
        )
    if event_type == "priority_change":
        return run_priority_change(base_jobs, params.get("changes", []), **kw)
    if event_type == "order_cancel":
        return run_order_cancel(base_jobs, params.get("job_names", []), **kw)
    if event_type == "quantity_change":
        return run_quantity_change(base_jobs, params.get("changes", []), **kw)
    return {"error": f"unknown event_type: {event_type}"}
