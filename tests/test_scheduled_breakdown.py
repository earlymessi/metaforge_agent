"""预约故障：仿真时钟触发自动重排。"""

from metaforge.services.production_execution import _scheduled_breakdown_ready


def test_scheduled_breakdown_ready_when_sim_reaches_start():
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
    assert _scheduled_breakdown_ready(doc) is True


def test_scheduled_breakdown_not_ready_before_start():
    doc = {
        "status": "running",
        "sim_time": 2.0,
        "scheduled_breakdown": {
            "status": "pending",
            "breakdown_start": 4.0,
        },
    }
    assert _scheduled_breakdown_ready(doc) is False


def test_scheduled_breakdown_not_ready_when_paused():
    doc = {
        "status": "paused",
        "sim_time": 5.0,
        "scheduled_breakdown": {
            "status": "pending",
            "breakdown_start": 4.0,
        },
    }
    assert _scheduled_breakdown_ready(doc) is False


def test_scheduled_breakdown_not_ready_after_fired():
    doc = {
        "status": "running",
        "sim_time": 5.0,
        "scheduled_breakdown": {
            "status": "fired",
            "breakdown_start": 4.0,
        },
    }
    assert _scheduled_breakdown_ready(doc) is False
