"""设备故障 R0/R1/R2 恢复重排。"""

from unittest.mock import patch

from metaforge.services.event_reschedule import run_machine_breakdown
from metaforge.utils.gantt_propagate import propagate_breakdown_on_gantt


def _minimal_jobs():
    return [
        {
            "name": "J1",
            "priority": 10,
            "tasks": [
                {"name": "O1", "machine_id": 2, "duration": 4},
                {"name": "O2", "machine_id": 0, "duration": 3},
            ],
        }
    ]


def test_r1_propagate_increases_makespan_when_breakdown_hits():
    gantt = [
        {"job_id": 0, "machine_id": 2, "operation_id": 0, "start": 0.0, "end": 4.0},
        {"job_id": 0, "machine_id": 0, "operation_id": 1, "start": 4.0, "end": 7.0},
    ]
    r1 = propagate_breakdown_on_gantt(
        gantt, machine_id=2, breakdown_start=1.0, breakdown_duration=5.0
    )
    assert max(op["end"] for op in r1) >= max(op["end"] for op in gantt)


def test_r2_uses_only_baseline_solver():
    seen = []

    def fake_compare(solvers, problem, **kwargs):
        seen.extend(solvers)
        gantt = [
            {"job_id": 0, "machine_id": 2, "operation_id": 0, "start": 5.0, "end": 9.0},
            {"job_id": 0, "machine_id": 0, "operation_id": 1, "start": 9.0, "end": 12.0},
        ]
        return {
            solvers[0]: {
                "gantt_data": gantt,
                "best_score": 12,
                "metrics": {"makespan": 12, "weighted_tardiness_total": 0},
            }
        }

    baseline_gantt = [
        {"job_id": 0, "machine_id": 2, "operation_id": 0, "start": 0.0, "end": 4.0},
        {"job_id": 0, "machine_id": 0, "operation_id": 1, "start": 4.0, "end": 7.0},
    ]

    with patch(
        "metaforge.services.event_reschedule.compare_solvers",
        side_effect=fake_compare,
    ):
        out = run_machine_breakdown(
            _minimal_jobs(),
            machine_id=2,
            breakdown_start=0.0,
            breakdown_duration=2.0,
            freeze_time=0.0,
            baseline_gantt=baseline_gantt,
            baseline_solver="ga",
            solvers=["ts", "spt"],
        )

    assert seen == ["ga"]
    assert out["status"] == "success"
    impact = out["data"]["impact_report"]
    assert "scenarios" in impact
    assert impact["scenarios"]["r0"]["label"] == "原计划"
    assert "r1_gantt" in impact
    assert "r2_gantt" in impact
    assert len(impact["r2_gantt"]) > 0


def test_machine_breakdown_includes_commitment_changes():
    baseline_gantt = [
        {"job_id": 0, "machine_id": 2, "operation_id": 0, "start": 0.0, "end": 4.0},
        {"job_id": 0, "machine_id": 0, "operation_id": 1, "start": 4.0, "end": 7.0},
    ]

    def fake_compare(solvers, problem, **kwargs):
        gantt = [
            {"job_id": 0, "machine_id": 2, "operation_id": 0, "start": 5.0, "end": 9.0},
            {"job_id": 0, "machine_id": 0, "operation_id": 1, "start": 9.0, "end": 12.0},
        ]
        return {
            solvers[0]: {
                "gantt_data": gantt,
                "best_score": 12,
                "metrics": {"makespan": 12, "weighted_tardiness_total": 0},
            }
        }

    with patch(
        "metaforge.services.event_reschedule.compare_solvers",
        side_effect=fake_compare,
    ):
        out = run_machine_breakdown(
            _minimal_jobs(),
            machine_id=2,
            breakdown_start=0.0,
            breakdown_duration=2.0,
            freeze_time=0.0,
            baseline_gantt=baseline_gantt,
            baseline_solver="spt",
        )

    impact = out["data"]["impact_report"]
    assert isinstance(impact.get("commitment_changes"), list)
    assert impact.get("scenarios")


def test_align_breakdown_times_uses_sim_when_llm_sent_zero():
    from metaforge.services.event_reschedule import _align_machine_breakdown_times

    p = _align_machine_breakdown_times(
        {"machine_id": 2, "breakdown_start": 0.0, "breakdown_duration": 3.0, "freeze_time": 0.0},
        {"status": "running", "sim_time": 10.0},
    )
    assert p["breakdown_start"] == 10.0
    assert p["freeze_time"] == 10.0
