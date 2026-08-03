"""Golden: when every candidate violates hard constraints, no recommendation."""

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


def test_all_illegal_candidates_yield_no_recommendation():
    strategy = SchedulingStrategy(
        hard_constraints=[
            Constraint(type="order_on_time", params={"job_id": "A", "due_date": 5}),
        ],
        objectives={"makespan": 1.0, "weighted_tardiness_total": 1.0},
    )
    candidates = [
        _candidate(
            "c1",
            {"A": 12},
            {
                "makespan": 12,
                "weighted_tardiness_total": 7,
                "energy_cost": 0,
                "machine_busy_cv": 0,
            },
        ),
        _candidate(
            "c2",
            {"A": 20},
            {
                "makespan": 20,
                "weighted_tardiness_total": 15,
                "energy_cost": 0,
                "machine_busy_cv": 0,
            },
        ),
    ]

    result = evaluate_candidates(
        strategy,
        candidates,
        jobs=[{"job_id": "A", "due_date": 5}],
    )

    assert result["recommended_schedule_id"] is None
    assert len(result["hard_violations"]) >= 2
