from metaforge.strategy.pipeline import run_planning


def test_pipeline_skip_hitl_returns_package(monkeypatch):
    def fake_solve(strategy, problem, policy):
        return [{
            "schedule_id": "ts",
            "solver": "ts",
            "metrics": {"makespan": 10, "weighted_tardiness_total": 0, "energy_cost": 0, "machine_busy_cv": 0.1},
            "completion_by_job": {"A": 5},
            "gantt_data": [],
        }]
    monkeypatch.setattr("metaforge.strategy.pipeline.solve_candidates", fake_solve)
    pkg = run_planning(
        user_goal="综合平衡",
        jobs=[{"job_id": "A", "due_date": 20, "operations": []}],
        machines=["M01"],
        skip_strategy_hitl=True,
        llm_client=None,
    )
    assert pkg["status"] == "COMPLETED"
    assert pkg.get("package", {}).get("recommended_schedule_id") is not None or pkg.get("evaluation")


def test_pipeline_waits_for_hitl_when_not_skipped():
    out = run_planning(
        user_goal="综合平衡",
        jobs=[{"job_id": "A", "due_date": 20}],
        machines=["M01"],
        skip_strategy_hitl=False,
        llm_client=None,
    )
    assert out["status"] == "WAITING_APPROVAL"
    assert out.get("strategy_draft") is not None
