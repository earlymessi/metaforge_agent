"""插单 / 改交期重排与 MES 基准甘特集成测试。"""

from unittest.mock import patch

from metaforge.services.event_reschedule import (
    dispatch_event_reschedule,
    run_due_date_change,
    run_insert_order,
)


def _jobs():
    return [
        {
            "name": "J1",
            "priority": 10,
            "tasks": [
                {"name": "O1", "machine_id": 0, "duration": 5},
                {"name": "O2", "machine_id": 1, "duration": 3},
            ],
        }
    ]


def _baseline_gantt():
    return [
        {"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0.0, "end": 5.0, "job_name": "J1"},
        {"job_id": 0, "machine_id": 1, "operation_id": 1, "start": 5.0, "end": 8.0, "job_name": "J1"},
    ]


def test_insert_local_repair_uses_baseline_gantt_without_resolving():
    seen = []

    def fake_compare(solvers, problem, **kwargs):
        seen.append(list(solvers))
        gantt = [
            {"job_id": 0, "machine_id": 1, "operation_id": 1, "start": 5.0, "end": 8.0, "job_name": "J1"},
            {"job_id": 1, "machine_id": 0, "operation_id": 0, "start": 5.0, "end": 10.0, "job_name": "急单"},
        ]
        return {solvers[0]: {"gantt_data": gantt, "best_score": 10, "metrics": {"makespan": 10}}}

    insert_job = {
        "name": "急单",
        "priority": 100,
        "tasks": [{"name": "X", "machine_id": 0, "duration": 5}],
    }

    with patch("metaforge.services.event_reschedule.compare_solvers", side_effect=fake_compare):
        out = run_insert_order(
            _jobs(),
            insert_job,
            freeze_time=3.0,
            mode="local_repair",
            baseline_gantt=_baseline_gantt(),
            baseline_solver="ga",
            solvers=["ts", "spt"],
        )

    assert out["status"] == "success"
    assert seen == [["ga"]]
    impact = out["data"]["impact_report"]
    assert impact["event_type"] == "insert_order"
    assert out["data"].get("updated_jobs")
    assert len(impact["r1_gantt"]) >= 2
    assert len(impact["r2_gantt"]) >= 2
    assert impact["scenarios"]["r1"]["label"] == "插单往后排"
    assert impact["scenarios"]["r2"]["label"] == "重调度后"
    ins_ops = [op for op in impact["r1_gantt"] if op["job_id"] == 1]
    assert ins_ops and ins_ops[0]["start"] >= 8.0


def test_due_date_dispatch_with_execution_baseline():
    seen = []

    def fake_compare(solvers, problem, **kwargs):
        seen.append(list(solvers))
        return {
            solvers[0]: {
                "gantt_data": [
                    {"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0.0, "end": 5.0, "job_name": "J1"},
                ],
                "best_score": 5,
                "metrics": {"makespan": 5, "weighted_tardiness_total": 0},
            }
        }

    envelope = {
        "event_type": "due_date_change",
        "base_jobs": _jobs(),
        "params": {"due_date_changes": [{"job_name": "J1", "new_due_date": 20.0}]},
        "reschedule_options": {"solvers": ["ga"], "baseline_gantt": _baseline_gantt(), "baseline_solver": "ga"},
        "production_execution": {"status": "running", "sim_time": 2.0, "jobs_snapshot": _jobs()},
    }

    with patch("metaforge.services.event_reschedule.compare_solvers", side_effect=fake_compare):
        out = dispatch_event_reschedule(envelope)

    assert out["status"] == "success"
    assert seen[0] == ["ga"]
    assert out["data"]["updated_jobs"][0]["due_date"] == 20.0
    impact = out["data"]["impact_report"]
    assert impact["event_type"] == "due_date_change"
    assert len(impact["r1_gantt"]) >= 1
    assert len(impact["r2_gantt"]) >= 1
    assert impact["scenarios"]["r1"]["label"] == "改期不重排"
    assert impact["scenarios"]["r2"]["label"] == "重调度后"


def test_due_date_change_dual_gantt_r1_equals_baseline_schedule():
    def fake_compare(solvers, problem, **kwargs):
        return {
            solvers[0]: {
                "gantt_data": [
                    {"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0.0, "end": 8.0, "job_name": "J1"},
                ],
                "best_score": 8,
                "metrics": {"makespan": 8, "weighted_tardiness_total": 1},
            }
        }

    base = _baseline_gantt()
    with patch("metaforge.services.event_reschedule.compare_solvers", side_effect=fake_compare):
        out = run_due_date_change(
            _jobs(),
            [{"job_name": "J1", "new_due_date": 12.0}],
            baseline_gantt=base,
            baseline_solver="ga",
            solvers=["ga"],
        )

    impact = out["data"]["impact_report"]
    assert impact["r1_gantt"] == base
    assert impact["r2_gantt"][0]["start"] == 0.0
