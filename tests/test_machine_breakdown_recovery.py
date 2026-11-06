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


def _op_overlaps(op, b0, b1):
    return float(op["start"]) < b1 - 1e-9 and float(op["end"]) > b0 + 1e-9


def test_r2_must_not_schedule_over_breakdown_window():
    """冻结时刻略晚于工序开工时，故障机台上跨故障窗的工序不得整段冻进 R2。"""
    jobs = [
        {
            "name": "J1",
            "priority": 10,
            "tasks": [
                {"name": "O1", "machine_id": 0, "duration": 8},
                {"name": "O2", "machine_id": 2, "duration": 6},
            ],
        },
        {
            "name": "J2",
            "priority": 10,
            "tasks": [
                {"name": "O1", "machine_id": 1, "duration": 7},
                {"name": "O2", "machine_id": 3, "duration": 5},
            ],
        },
    ]
    baseline_gantt = [
        {"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0.0, "end": 8.0, "job_name": "J1"},
        {"job_id": 0, "machine_id": 2, "operation_id": 1, "start": 8.0, "end": 14.0, "job_name": "J1"},
        {"job_id": 1, "machine_id": 1, "operation_id": 0, "start": 0.0, "end": 7.0, "job_name": "J2"},
        {"job_id": 1, "machine_id": 3, "operation_id": 1, "start": 7.0, "end": 12.0, "job_name": "J2"},
    ]
    b0, dur = 0.4, 4.0
    b1 = b0 + dur

    out = run_machine_breakdown(
        jobs,
        machine_id=0,
        breakdown_start=b0,
        breakdown_duration=dur,
        freeze_time=b0,
        baseline_gantt=baseline_gantt,
        baseline_solver="spt",
        solvers=["spt"],
    )
    assert "error" not in out, out
    impact = out["data"]["impact_report"]
    r2 = impact["r2_gantt"]

    overlapping = [
        op
        for op in r2
        if int(op["machine_id"]) == 0 and _op_overlaps(op, b0, b1)
    ]
    assert overlapping == [], f"R2 不得覆盖故障窗 [{b0},{b1}]: {overlapping}"


def test_r2_can_start_early_on_alternate_machine():
    """有替代机台时，残段应可在 freeze 后立刻上替代机，不必干等到故障结束。"""
    jobs = [
        {
            "name": "J1",
            "priority": 10,
            "tasks": [
                {
                    "name": "O1",
                    "machine_id": 0,
                    "machine_options": [0, 4],
                    "duration": 8,
                },
                {"name": "O2", "machine_id": 2, "duration": 6},
            ],
        },
        {
            "name": "J2",
            "priority": 10,
            "tasks": [
                {"name": "O1", "machine_id": 1, "duration": 7},
                {"name": "O2", "machine_id": 3, "duration": 5},
            ],
        },
    ]
    baseline_gantt = [
        {"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0.0, "end": 8.0, "job_name": "J1"},
        {"job_id": 0, "machine_id": 2, "operation_id": 1, "start": 8.0, "end": 14.0, "job_name": "J1"},
        {"job_id": 1, "machine_id": 1, "operation_id": 0, "start": 0.0, "end": 7.0, "job_name": "J2"},
        {"job_id": 1, "machine_id": 3, "operation_id": 1, "start": 7.0, "end": 12.0, "job_name": "J2"},
    ]
    b0, dur = 0.3, 4.0
    out = run_machine_breakdown(
        jobs,
        machine_id=0,
        breakdown_start=b0,
        breakdown_duration=dur,
        freeze_time=b0,
        baseline_gantt=baseline_gantt,
        baseline_solver="spt",
        solvers=["spt"],
    )
    assert "error" not in out, out
    r2 = out["data"]["impact_report"]["r2_gantt"]
    j1_first = next(
        op
        for op in r2
        if int(op["job_id"]) == 0 and int(op.get("operation_id", 0)) == 0
    )
    assert int(j1_first["machine_id"]) != 0, j1_first
    assert float(j1_first["start"]) <= b0 + 1e-6, (
        f"有替代机时应约从 freeze={b0} 开工，实际 start={j1_first['start']}"
    )
    assert not _op_overlaps(j1_first, b0, b0 + dur) or int(j1_first["machine_id"]) != 0
