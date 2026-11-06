from metaforge.fab.evaluate import check_hard
from metaforge.strategy.evaluator import evaluate_candidates
from metaforge.strategy.models import Constraint, SchedulingStrategy


def _photo_jobs():
    return [
        {
            "job_id": "L1",
            "name": "L1",
            "tasks": [
                {
                    "name": "photo_L1",
                    "process_area": "photo",
                    "is_dedication_mark": True,
                    "machine_id": 0,
                    "duration": 5,
                },
                {"name": "etch_1", "process_area": "etch", "machine_id": 2, "duration": 3},
                {
                    "name": "photo_L2",
                    "process_area": "photo",
                    "machine_id": 1,
                    "duration": 5,
                },
            ],
        }
    ]


def test_dedication_violation_when_photo_cross_machine():
    strategy = SchedulingStrategy(
        hard_constraints=[Constraint(type="photo_machine_dedication", params={})]
    )
    candidate = {
        "schedule_id": "manual",
        "gantt_data": [
            {
                "job_id": 0,
                "operation_name": "photo_L1",
                "machine_id": 0,
                "start": 0,
                "end": 5,
            },
            {
                "job_id": 0,
                "operation_name": "etch_1",
                "machine_id": 2,
                "start": 5,
                "end": 8,
            },
            {
                "job_id": 0,
                "operation_name": "photo_L2",
                "machine_id": 1,
                "start": 8,
                "end": 13,
            },
        ],
        "metrics": {"makespan": 13},
    }
    ok, viol = check_hard(strategy, candidate, jobs=_photo_jobs())
    assert ok is False
    assert any(v["type"] == "photo_machine_dedication" for v in viol)


def test_dedication_ok_same_machine():
    strategy = SchedulingStrategy(
        hard_constraints=[Constraint(type="photo_machine_dedication", params={})]
    )
    candidate = {
        "schedule_id": "manual",
        "gantt_data": [
            {
                "job_id": 0,
                "operation_name": "photo_L1",
                "machine_id": 0,
                "start": 0,
                "end": 5,
            },
            {
                "job_id": 0,
                "operation_name": "photo_L2",
                "machine_id": 0,
                "start": 5,
                "end": 10,
            },
        ],
        "metrics": {"makespan": 10},
    }
    ok, viol = check_hard(strategy, candidate, jobs=_photo_jobs())
    assert ok is True
    assert viol == []


def test_max_lag_violation():
    strategy = SchedulingStrategy(
        hard_constraints=[
            Constraint(
                type="max_lag_between_ops",
                params={"from_op": "wet_clean", "to_op": "diffusion", "max_lag": 1.5},
            )
        ]
    )
    jobs = [
        {
            "job_id": "L1",
            "tasks": [
                {"name": "wet_clean", "duration": 2},
                {"name": "diffusion", "duration": 8},
            ],
        }
    ]
    candidate = {
        "gantt_data": [
            {"job_id": 0, "operation_name": "wet_clean", "machine_id": 0, "start": 0, "end": 2},
            {"job_id": 0, "operation_name": "diffusion", "machine_id": 1, "start": 5, "end": 13},
        ],
        "metrics": {},
    }
    ok, viol = check_hard(strategy, candidate, jobs=jobs)
    assert ok is False
    assert any(v["type"] == "max_lag_between_ops" for v in viol)


def test_batch_skipped_without_structure():
    strategy = SchedulingStrategy(
        hard_constraints=[
            Constraint(type="batch_same_family", params={}),
            Constraint(type="batch_capacity", params={}),
        ]
    )
    ok, viol = check_hard(strategy, {"gantt_data": [], "metrics": {}}, jobs=[])
    assert ok is True
    assert viol == []


def test_evaluate_candidates_fab_domain_wires_check():
    strategy = SchedulingStrategy(
        hard_constraints=[Constraint(type="photo_machine_dedication", params={})],
        objectives={"makespan": 1.0},
    )
    candidates = [
        {
            "schedule_id": "bad",
            "gantt_data": [
                {
                    "job_id": 0,
                    "operation_name": "photo_L1",
                    "machine_id": 0,
                    "start": 0,
                    "end": 5,
                },
                {
                    "job_id": 0,
                    "operation_name": "photo_L2",
                    "machine_id": 1,
                    "start": 5,
                    "end": 10,
                },
            ],
            "metrics": {"makespan": 10},
        }
    ]
    # without domain: FAB type unknown to classic checker → skipped warning, hard_ok true
    classic = evaluate_candidates(strategy, candidates, jobs=_photo_jobs())
    assert classic["ranking"][0]["hard_ok"] is True

    fab = evaluate_candidates(
        strategy, candidates, jobs=_photo_jobs(), domain="fab"
    )
    assert fab["ranking"][0]["hard_ok"] is False
