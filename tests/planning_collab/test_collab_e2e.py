"""S2 acceptance e2e: summarize skip + built_from_jobs + collab_trace."""

from metaforge.planning_collab.supervisor import run_collab


def _fake_solve(strategy, problem, policy, job_aliases=None):
    return (
        [
            {
                "schedule_id": "edd",
                "solver": "edd",
                "metrics": {
                    "makespan": 10,
                    "weighted_tardiness_total": 0,
                    "energy_cost": 0,
                    "machine_busy_cv": 0.1,
                },
                "completion_by_job": {"A": 5},
                "gantt_data": [],
            }
        ],
        [],
    )


def _sample_jobs():
    return [
        {
            "job_id": "A",
            "name": "A",
            "priority": 10,
            "due_date": 50,
            "tasks": [
                {"machine_id": 0, "duration": 2},
                {"machine_id": 1, "duration": 2},
            ],
        }
    ]


def test_summarize_failure_still_completes_with_recommendation(monkeypatch):
    """§9.3: Mock LLM summary failure → still skip HITL and get recommended."""

    class Boom:
        def complete(self, *a, **k):
            raise RuntimeError("llm down")

    monkeypatch.setattr(
        "metaforge.strategy.pipeline._solve_candidates_internal", _fake_solve
    )
    out = run_collab(
        user_goal="保证A按期，减少换型",
        jobs=_sample_jobs(),
        machines=["0", "1"],
        skip_strategy_hitl=True,
        llm_client=Boom(),
    )
    assert out["status"] == "COMPLETED"
    assert out.get("package", {}).get("recommended_schedule_id") is not None
    # Summaries skipped (None); structure still present.
    order = (out.get("artifacts") or {}).get("order_analysis") or {}
    assert "critical_orders" in order
    assert order.get("reasoning_summary") in (None, "")
    # Trace includes agents even when reasoning_summary empty.
    agents = (out.get("collab_trace") or {}).get("agents") or []
    assert len(agents) == 3
    assert all(a.get("reasoning_summary") in (None, "") for a in agents)


def test_collab_e2e_built_from_jobs_and_recommended(monkeypatch):
    """§9.5: collab → skip HITL → built_from_jobs + recommended."""
    monkeypatch.setattr(
        "metaforge.strategy.pipeline._solve_candidates_internal", _fake_solve
    )
    out = run_collab(
        user_goal="综合平衡",
        jobs=_sample_jobs(),
        machines=["0", "1"],
        skip_strategy_hitl=True,
        llm_client=None,
        problem=None,
    )
    assert out["status"] == "COMPLETED"
    pkg = out.get("package") or {}
    assert pkg.get("recommended_schedule_id") is not None
    problem_meta = pkg.get("problem_meta") or {}
    assert problem_meta.get("built_from_jobs") is True

    trace = out.get("collab_trace") or {}
    assert trace.get("type") == "collab_trace"
    assert len(trace.get("agents") or []) == 3
    assert trace.get("strategy_trace") is not None
    assert "order_analysis" in (out.get("artifacts") or {})
