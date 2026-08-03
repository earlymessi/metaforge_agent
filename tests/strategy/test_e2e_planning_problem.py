"""S1 补洞：jobs → problem 自动构建 + HITL resume 真求解。"""

from metaforge.strategy.hitl import approve_strategy
from metaforge.strategy.models import SolverPolicy
from metaforge.strategy.pipeline import resume_planning, run_planning
from metaforge.strategy.problem_resolve import resolve_planning_problem


def _tiny_jobs():
    return [
        {
            "job_id": "A",
            "name": "A",
            "priority": 10,
            "due_date": 50,
            "tasks": [
                {"machine_id": 0, "duration": 2, "name": "A1"},
                {"machine_id": 1, "duration": 3, "name": "A2"},
            ],
        },
        {
            "job_id": "B",
            "name": "B",
            "priority": 5,
            "due_date": 50,
            "tasks": [{"machine_id": 0, "duration": 2, "name": "B1"}],
        },
    ]


def _fast_policy(strategy, n_jobs=0):
    return SolverPolicy(
        primary_solvers=["edd"],
        fallback_solver="spt",
        time_budget_seconds=2.0,
        max_candidates=2,
        parameters={},
        reason="e2e-fast",
    )


def test_resolve_planning_problem_from_jobs():
    problem, meta = resolve_planning_problem(_tiny_jobs())
    assert problem is not None
    assert meta["built_from_jobs"] is True
    assert "A" in meta["job_aliases"]["0"] or any(
        "A" in v for v in meta["job_aliases"].values()
    )


def test_e2e_skip_hitl_builds_problem_and_recommends(monkeypatch):
    monkeypatch.setattr("metaforge.strategy.pipeline.build_solver_policy", _fast_policy)
    out = run_planning(
        user_goal="综合平衡排程",
        jobs=_tiny_jobs(),
        machines=["0", "1"],
        skip_strategy_hitl=True,
        llm_client=None,
    )
    assert out["status"] == "COMPLETED"
    pkg = out["package"]
    assert pkg["problem_meta"]["built_from_jobs"] is True
    assert pkg["recommended_schedule_id"] is not None
    assert out.get("candidate_schedules")


def test_e2e_hitl_approve_resumes_without_client_problem(monkeypatch):
    monkeypatch.setattr("metaforge.strategy.pipeline.build_solver_policy", _fast_policy)
    waiting = run_planning(
        user_goal="优先交付，保证客户A按期",
        jobs=_tiny_jobs(),
        machines=["0", "1"],
        skip_strategy_hitl=False,
        llm_client=None,
    )
    assert waiting["status"] == "WAITING_APPROVAL"
    run_id = waiting["run_id"]

    approved = approve_strategy(run_id)
    assert approved["status"] == "RUNNING"

    # UI 当前不传 problem：后端应从 run.jobs 自动构建
    done = resume_planning(run_id)
    assert done["status"] == "COMPLETED"
    assert done["package"]["recommended_schedule_id"] is not None
    assert done["package"]["problem_meta"]["built_from_jobs"] is True


def test_fallback_solver_used_when_primary_fails(monkeypatch):
    from metaforge.strategy.models import SchedulingStrategy
    from metaforge.strategy.pipeline import _solve_candidates_internal

    problem, meta = resolve_planning_problem(_tiny_jobs())
    strategy = SchedulingStrategy(
        base_template="balanced",
        objectives={"makespan": 1.0, "weighted_tardiness_total": 0.5, "energy_cost": 0.05, "machine_busy_cv": 1.0},
    )
    policy = SolverPolicy(
        primary_solvers=["__no_such_solver__"],
        fallback_solver="edd",
        time_budget_seconds=2.0,
        max_candidates=1,
        parameters={},
        reason="fallback-test",
    )
    cands, failed = _solve_candidates_internal(
        strategy, problem, policy, job_aliases=meta.get("job_aliases")
    )
    assert failed
    assert cands
    assert cands[0]["solver"] == "edd"
