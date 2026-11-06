"""预约动态事件：仿真时钟触发自动重排。"""

from metaforge.services.production_execution import (
    _scheduled_event_ready,
    _validate_scheduled_params,
    get_scheduled_event,
)


def test_scheduled_event_ready_when_sim_reaches_trigger():
    doc = {
        "status": "running",
        "sim_time": 5.0,
        "scheduled_event": {
            "status": "pending",
            "event_type": "material_delay",
            "trigger_at": 4.0,
            "params": {"job_name": "J1", "delay_hours": 2},
        },
    }
    assert _scheduled_event_ready(doc) is True


def test_scheduled_event_not_ready_before_trigger():
    doc = {
        "status": "running",
        "sim_time": 2.0,
        "scheduled_event": {
            "status": "pending",
            "event_type": "order_cancel",
            "trigger_at": 4.0,
            "params": {"job_names": ["J1"]},
        },
    }
    assert _scheduled_event_ready(doc) is False


def test_legacy_breakdown_still_ready():
    doc = {
        "status": "running",
        "sim_time": 5.0,
        "scheduled_breakdown": {
            "status": "pending",
            "breakdown_start": 4.0,
            "machine_id": 3,
            "breakdown_duration": 4,
        },
    }
    assert _scheduled_event_ready(doc) is True
    se = get_scheduled_event(doc)
    assert se["event_type"] == "machine_breakdown"
    assert se["trigger_at"] == 4.0


def test_validate_insert_order_params():
    p = _validate_scheduled_params(
        "insert_order",
        {"insert_job": {"name": "急单", "tasks": [{"machine_id": 0, "duration": 3}]}},
    )
    assert p["mode"] == "local_repair"


def test_validate_rejects_unknown_missing_fields():
    try:
        _validate_scheduled_params("due_date_change", {})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "due_date_changes" in str(e)
