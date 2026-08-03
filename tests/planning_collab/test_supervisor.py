from metaforge.planning_collab.supervisor import run_collab, run_collab_analyze


def test_supervisor_analyze_fills_artifacts():
    out = run_collab_analyze(
        user_goal="保证A按期，减少换型",
        jobs=[
            {
                "job_id": "A",
                "due_date": 10,
                "priority": 8,
                "tasks": [{"machine_id": 0, "duration": 2}],
            }
        ],
        machines=["0"],
        llm_client=None,
    )
    arts = out["artifacts"]
    assert "order_analysis" in arts
    assert "constraint_analysis" in arts
    assert "resource_analysis" in arts
    assert "A" in (arts["order_analysis"].get("critical_orders") or [])
    soft_types = [c["type"] for c in arts["constraint_analysis"].get("soft_constraints") or []]
    assert "reduce_changeover" in soft_types


def test_supervisor_run_skip_hitl(monkeypatch):
    def fake_internal(strategy, problem, policy, job_aliases=None):
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

    monkeypatch.setattr(
        "metaforge.strategy.pipeline._solve_candidates_internal", fake_internal
    )
    out = run_collab(
        user_goal="综合平衡",
        jobs=[
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
        ],
        machines=["0", "1"],
        skip_strategy_hitl=True,
        llm_client=None,
    )
    assert out["status"] == "COMPLETED"
    assert out.get("package", {}).get("recommended_schedule_id") is not None
    assert "order_analysis" in out.get("artifacts", {})
