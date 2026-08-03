from __future__ import annotations

from typing import Any, Dict, List, Tuple

from metaforge.strategy.adapters import strategy_to_solver_inputs
from metaforge.strategy.evaluator import evaluate_candidates
from metaforge.strategy.generator import generate_strategy
from metaforge.strategy.models import SchedulingStrategy, SolverPolicy
from metaforge.strategy.run_state import create_run, get_run, update_run
from metaforge.strategy.solver_policy import build_solver_policy
from metaforge.strategy.trace import build_strategy_trace


def _policy_to_dict(policy: SolverPolicy) -> Dict[str, Any]:
    return {
        "primary_solvers": list(policy.primary_solvers),
        "fallback_solver": policy.fallback_solver,
        "time_budget_seconds": policy.time_budget_seconds,
        "max_candidates": policy.max_candidates,
        "reason": policy.reason,
    }


def _solve_candidates_internal(
    strategy: SchedulingStrategy,
    problem: Any,
    policy: SolverPolicy,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if problem is None:
        return [], []

    from metaforge.utils.compare_solvers import run_single_solver

    weights, hints = strategy_to_solver_inputs(strategy)
    resource_config = hints.get("resource_config_patch")

    candidates: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    for solver_id in policy.primary_solvers:
        params = (policy.parameters or {}).get(solver_id)
        try:
            sr = run_single_solver(
                solver_id,
                problem,
                weights=weights,
                resource_config=resource_config,
                solver_params=params,
            )
            candidates.append(
                {
                    "schedule_id": sr.solver_id,
                    "solver": sr.solver_id,
                    "metrics": dict(sr.metrics or {}),
                    "gantt_data": list(sr.gantt_data or []),
                }
            )
        except Exception as exc:  # noqa: BLE001 - continue other solvers
            failed.append({"solver": solver_id, "error": str(exc)})

    return candidates, failed


def solve_candidates(
    strategy: SchedulingStrategy,
    problem: Any,
    policy: SolverPolicy,
) -> List[Dict[str, Any]]:
    """Run primary solvers; return [] when problem is None."""
    candidates, _ = _solve_candidates_internal(strategy, problem, policy)
    return candidates


def _finish_planning(
    run_id: str,
    *,
    strategy: SchedulingStrategy,
    jobs: Any,
    problem: Any,
) -> Dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise KeyError(f"run not found: {run_id!r}")

    policy = build_solver_policy(strategy, n_jobs=len(list(jobs or [])))
    policy_dict = _policy_to_dict(policy)

    candidates, failed_solvers = _solve_candidates_internal(strategy, problem, policy)
    evaluation = evaluate_candidates(strategy, candidates, jobs=jobs)

    warnings = list(run.get("warnings") or [])
    warnings.extend(evaluation.get("warnings") or [])

    package = {
        "recommended_schedule_id": evaluation["recommended_schedule_id"],
        "evaluation": evaluation,
        "failed_solvers": failed_solvers,
        "strategy": strategy.to_dict(),
    }

    run = update_run(
        run_id,
        stage="done",
        status="COMPLETED",
        candidate_schedules=candidates,
        evaluation=evaluation,
        package=package,
        solver_policy=policy_dict,
        failed_solvers=failed_solvers,
        warnings=warnings,
        stages=["generate", "validate", "solve", "evaluate"],
    )

    trace = build_strategy_trace(run)
    return update_run(run_id, strategy_trace=trace, execution_trace=trace)


def run_planning(
    *,
    user_goal: str,
    jobs: Any,
    machines: Any,
    skip_strategy_hitl: bool = False,
    llm_client: Any = None,
    problem: Any = None,
    workers: Any = None,
    tools: Any = None,
    allow_simulated: bool = True,
    **kwargs: Any,
) -> Dict[str, Any]:
    run = create_run(
        user_goal=user_goal,
        jobs=list(jobs or []),
        machines=list(machines or []),
        stage="generate",
        status="RUNNING",
    )

    strategy, gen_meta = generate_strategy(
        user_goal=user_goal,
        jobs=jobs,
        machines=machines,
        llm_client=llm_client,
        workers=workers,
        tools=tools,
        allow_simulated=allow_simulated,
    )

    warnings = list(run.get("warnings") or [])
    if gen_meta.get("fallback"):
        warnings.append("strategy generated via rule_fallback")

    strategy_dict = strategy.to_dict()

    update_run(
        run["run_id"],
        stage="generate",
        strategy_draft=strategy_dict,
        generation_meta=gen_meta,
        warnings=warnings,
    )

    if not skip_strategy_hitl:
        return update_run(
            run["run_id"],
            status="WAITING_APPROVAL",
            stage="hitl_strategy",
            strategy_draft=strategy_dict,
            stages=["generate", "validate", "hitl_strategy"],
        )

    update_run(
        run["run_id"],
        strategy_approved=strategy_dict,
        stage="solve",
        status="RUNNING",
    )

    return _finish_planning(
        run["run_id"],
        strategy=strategy,
        jobs=jobs,
        problem=problem,
    )


def resume_planning(run_id: str, *, problem: Any = None) -> Dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise KeyError(f"run not found: {run_id!r}")

    approved = run.get("strategy_approved")
    if not approved:
        return update_run(
            run_id,
            status="FAILED",
            error="no strategy_approved; approve before resume",
        )

    strategy = SchedulingStrategy.from_dict(approved)
    jobs = run.get("jobs") or []

    update_run(run_id, stage="solve", status="RUNNING")
    return _finish_planning(
        run_id,
        strategy=strategy,
        jobs=jobs,
        problem=problem,
    )
