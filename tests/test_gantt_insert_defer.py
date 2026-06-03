"""插单往后排 R1 甘特推演。"""

from metaforge.utils.gantt_insert_defer import defer_insert_to_tail_gantt


def test_defer_insert_appends_after_baseline_tail():
    baseline = [
        {"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0.0, "end": 5.0},
        {"job_id": 0, "machine_id": 1, "operation_id": 1, "start": 5.0, "end": 8.0},
    ]
    insert_job = {
        "name": "急单",
        "priority": 100,
        "tasks": [{"name": "X", "machine_id": 0, "duration": 4}],
    }
    out = defer_insert_to_tail_gantt(baseline, insert_job, insert_job_id=1, freeze_time=0.0)
    assert len(out) == 3
    assert out[0]["end"] == 5.0
    assert out[1]["end"] == 8.0
    ins = [op for op in out if op["job_id"] == 1][0]
    assert ins["start"] == 8.0
    assert ins["end"] == 12.0
