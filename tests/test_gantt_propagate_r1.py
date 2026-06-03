from metaforge.utils.gantt_propagate import propagate_breakdown_on_gantt


def test_r1_shifts_op_crossing_breakdown_window():
    gantt = [
        {"job_id": 0, "machine_id": 2, "operation_id": 0, "start": 10.0, "end": 14.0},
    ]
    out = propagate_breakdown_on_gantt(
        gantt,
        machine_id=2,
        breakdown_start=12.0,
        breakdown_duration=4.0,
    )
    assert out[0]["start"] >= 16.0
    assert out[0]["end"] > out[0]["start"]


def test_r1_preserves_job_order():
    gantt = [
        {"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0.0, "end": 3.0},
        {"job_id": 0, "machine_id": 1, "operation_id": 1, "start": 3.0, "end": 6.0},
        {"job_id": 1, "machine_id": 2, "operation_id": 0, "start": 0.0, "end": 5.0},
    ]
    out = propagate_breakdown_on_gantt(
        gantt,
        machine_id=2,
        breakdown_start=1.0,
        breakdown_duration=10.0,
    )
    assert len(out) == 3
    assert out[2]["job_id"] == 1
