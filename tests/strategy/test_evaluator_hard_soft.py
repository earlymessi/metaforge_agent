from metaforge.strategy.models import Constraint, SchedulingStrategy
from metaforge.strategy.evaluator import evaluate_candidates


def _cand(sid, completion_by_job, metrics, gantt=None):
    return {
        "schedule_id": sid,
        "solver": sid,
        "metrics": metrics,
        "completion_by_job": completion_by_job,
        "gantt_data": gantt or [],
    }


def test_hard_illegal_cannot_be_recommended():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="order_on_time", params={"job_id": "A", "due_date": 10})],
        objectives={"makespan": 1.0, "weighted_tardiness_total": 1.0},
    )
    cands = [
        _cand("bad", {"A": 20}, {"makespan": 20, "weighted_tardiness_total": 10, "energy_cost": 0, "machine_busy_cv": 0}),
        _cand("good", {"A": 8}, {"makespan": 30, "weighted_tardiness_total": 0, "energy_cost": 0, "machine_busy_cv": 0}),
    ]
    result = evaluate_candidates(s, cands, jobs=[{"job_id": "A", "due_date": 10}])
    assert result["recommended_schedule_id"] == "good"
    assert result["ranking"][0]["schedule_id"] == "good" or result["recommended_schedule_id"] == "good"


def test_all_illegal_returns_null_recommendation():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="order_on_time", params={"job_id": "A", "due_date": 1})],
        objectives={"makespan": 1.0},
    )
    cands = [_cand("x", {"A": 99}, {"makespan": 99, "weighted_tardiness_total": 98, "energy_cost": 0, "machine_busy_cv": 0})]
    result = evaluate_candidates(s, cands, jobs=[{"job_id": "A", "due_date": 1}])
    assert result["recommended_schedule_id"] is None
    assert result["hard_violations"]
