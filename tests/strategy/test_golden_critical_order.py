"""Golden: critical order on-time constraint picks the only legal candidate."""

from metaforge.strategy.evaluator import evaluate_candidates
from metaforge.strategy.models import Constraint, SchedulingStrategy


def _candidate(schedule_id, completion_by_job, metrics):
    return {
        "schedule_id": schedule_id,
        "solver": schedule_id,
        "metrics": metrics,
        "completion_by_job": completion_by_job,
        "gantt_data": [],
    }


def test_critical_order_recommends_only_on_time_candidate():
    strategy = SchedulingStrategy(
        hard_constraints=[
            Constraint(type="order_on_time", params={"job_id": "A", "due_date": 10}),
        ],
        objectives={"makespan": 1.0, "weighted_tardiness_total": 2.0},
    )
    candidates = [
        _candidate(
            "late",
            {"A": 15},
            {
                "makespan": 15,
                "weighted_tardiness_total": 5,
                "energy_cost": 0,
                "machine_busy_cv": 0,
            },
        ),
        _candidate(
            "on_time",
            {"A": 9},
            {
                "makespan": 25,
                "weighted_tardiness_total": 0,
                "energy_cost": 0,
                "machine_busy_cv": 0,
            },
        ),
    ]

    result = evaluate_candidates(
        strategy,
        candidates,
        jobs=[{"job_id": "A", "due_date": 10, "priority": 100}],
    )

    assert result["recommended_schedule_id"] == "on_time"
    assert any(v["schedule_id"] == "late" for v in result["hard_violations"])
