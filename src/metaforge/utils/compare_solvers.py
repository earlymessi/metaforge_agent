import copy
import random
import time

import numpy as np

from metaforge.metaforge_runner import run_solver
from metaforge.utils.metrics import (
    compute_bottleneck_report,
    compute_composite_score,
    compute_schedule_metrics,
)
from metaforge.utils.solve_result import SolveResult, normalize_solver_output
from metaforge.utils.solver_registry import get_solver_spec, resolve_solver_id


def run_single_solver(
    solver_name: str,
    problem,
    *,
    weights=None,
    resource_config=None,
    random_seed=None,
    solver_params=None,
    dynamic_events=None,
) -> SolveResult:
    """运行单个求解器并返回规范化的 SolveResult。"""
    if random_seed is not None:
        random.seed(int(random_seed))
        np.random.seed(int(random_seed))

    solver_id = resolve_solver_id(solver_name)
    spec = get_solver_spec(solver_id)
    display_name = spec.name_zh or spec.name_en

    problem_copy = copy.deepcopy(problem)
    events_copy = copy.deepcopy(dynamic_events) if dynamic_events else None

    output = run_solver(
        solver_id,
        problem_copy,
        dynamic_events=events_copy,
        weights=weights,
        resource_config=resource_config,
        solver_params=solver_params,
    )

    gantt_data = output.get("gantt_data", []) if isinstance(output, dict) else []
    metrics = compute_schedule_metrics(gantt_data, problem_copy, resource_config=resource_config)
    composite = float(compute_composite_score(metrics, weights=weights))

    result = normalize_solver_output(
        output,
        solver_id=solver_id,
        display_name=display_name,
        optimization_mode=spec.optimization_mode,
        metrics=metrics,
        composite_score=composite,
    )
    result.meta["bottleneck_report"] = compute_bottleneck_report(gantt_data, problem_copy)
    return result


def compare_solvers(
    solver_names,
    problem,
    track_schedule=True,
    dynamic_events=None,
    *,
    weights=None,
    resource_config=None,
    random_seed=None,
    solver_params=None,
):
    """
    运行多个算法，返回 JSON 友好的字典（键为 solver_id）。
    """
    del track_schedule

    if random_seed is not None:
        random.seed(int(random_seed))
        np.random.seed(int(random_seed))

    results = {}
    instance_name = getattr(problem, "instance_name", "Unknown Instance")
    print(f"Server: Starting comparison on {instance_name}...")

    params_by_solver = solver_params or {}

    for name in solver_names:
        solver_id = resolve_solver_id(name)
        spec = get_solver_spec(solver_id)
        display_name = spec.name_zh or spec.name_en
        print(f"Server: Running {display_name} ({solver_id})...")

        per_solver_params = params_by_solver.get(solver_id) or params_by_solver.get(name)

        try:
            sr = run_single_solver(
                solver_id,
                problem,
                weights=weights,
                resource_config=resource_config,
                random_seed=random_seed,
                solver_params=per_solver_params,
                dynamic_events=dynamic_events,
            )
            entry = sr.to_api_dict()
            entry["bottleneck_report"] = sr.meta.get("bottleneck_report", {})
            entry["supports_weights_in_search"] = spec.supports_weights_in_search
            entry["family"] = spec.family
            results[solver_id] = entry
        except Exception as e:
            print(f"Error running {solver_id}: {e}")
            results[solver_id] = {
                "id": solver_id,
                "name": f"{display_name} (Error)",
                "best_score": 0,
                "score": 0,
                "runtime_sec": 0,
                "history": [],
                "gantt_data": [],
                "metrics": {},
                "optimization_mode": spec.optimization_mode,
                "family": spec.family,
                "error": str(e),
            }

    return results
