"""预约动态事件：8 类校验、dispatch 响应与对比甘特。"""

import pytest

from metaforge.services.event_reschedule import dispatch_event_reschedule
from metaforge.services.production_execution import (
    SUPPORTED_SCHEDULED_EVENTS,
    _scheduled_event_ready,
    _validate_scheduled_params,
)


def _jobs():
    return [
        {
            "name": "工单A",
            "priority": 10,
            "due_date": 18.0,
            "quantity": 1,
            "tasks": [
                {"name": "O1", "machine_id": 0, "duration": 4},
                {"name": "O2", "machine_id": 1, "duration": 3},
            ],
        },
        {
            "name": "工单B",
            "priority": 20,
            "due_date": 22.0,
            "quantity": 1,
            "tasks": [
                {"name": "O1", "machine_id": 1, "duration": 5},
                {"name": "O2", "machine_id": 0, "duration": 2},
            ],
        },
    ]


def _baseline_gantt():
    return [
        {"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0.0, "end": 4.0, "job_name": "工单A"},
        {"job_id": 0, "machine_id": 1, "operation_id": 1, "start": 4.0, "end": 7.0, "job_name": "工单A"},
        {"job_id": 1, "machine_id": 1, "operation_id": 0, "start": 0.0, "end": 5.0, "job_name": "工单B"},
        {"job_id": 1, "machine_id": 0, "operation_id": 1, "start": 5.0, "end": 7.0, "job_name": "工单B"},
    ]


EVENT_CASES = [
    (
        "machine_breakdown",
        {
            "machine_id": 0,
            "breakdown_start": 1.0,
            "breakdown_duration": 3.0,
            "freeze_time": 1.0,
        },
    ),
    (
        "insert_order",
        {
            "mode": "local_repair",
            "freeze_time": 1.0,
            "insert_job": {
                "name": "急单",
                "priority": 100,
                "tasks": [{"name": "Op-1", "machine_id": 0, "duration": 2}],
            },
        },
    ),
    (
        "due_date_change",
        {"due_date_changes": [{"job_name": "工单A", "new_due_date": 10.0}]},
    ),
    (
        "planned_downtime",
        {
            "downtime_blocks": [
                {"machine_id": 0, "start": 1.0, "end": 4.0, "label": "停机"}
            ]
        },
    ),
    ("material_delay", {"job_name": "工单A", "delay_hours": 3.0}),
    ("priority_change", {"changes": [{"job_name": "工单A", "new_priority": 100}]}),
    ("order_cancel", {"job_names": ["工单B"]}),
    ("quantity_change", {"changes": [{"job_name": "工单A", "new_quantity": 3}]}),
]


def test_supported_scheduled_events_cover_eight():
    assert SUPPORTED_SCHEDULED_EVENTS == {et for et, _ in EVENT_CASES}


@pytest.mark.parametrize("event_type,params", EVENT_CASES)
def test_validate_scheduled_params_ok(event_type, params):
    out = _validate_scheduled_params(event_type, params)
    assert isinstance(out, dict)


@pytest.mark.parametrize("event_type,params", EVENT_CASES)
def test_scheduled_event_ready_for_each_type(event_type, params):
    doc = {
        "status": "running",
        "sim_time": 2.0,
        "scheduled_event": {
            "event_type": event_type,
            "trigger_at": 1.5,
            "params": params,
            "status": "pending",
        },
    }
    assert _scheduled_event_ready(doc) is True


@pytest.mark.parametrize("event_type,params", EVENT_CASES)
def test_dispatch_returns_dual_gantt_for_viz(event_type, params):
    raw = dispatch_event_reschedule(
        {
            "event_type": event_type,
            "base_jobs": _jobs(),
            "params": params,
            "reschedule_options": {
                "solvers": ["spt"],
                "random_seed": 1,
                "baseline_gantt": _baseline_gantt(),
                "baseline_solver": "spt",
            },
        }
    )
    assert "error" not in raw, raw.get("error")
    data = raw["data"]
    ir = data["impact_report"]
    assert ir.get("event_type") == event_type
    assert data.get("results"), event_type
    # 对比甘特：三场景事件或扩展事件都应有左右图
    assert ir.get("r1_gantt") or ir.get("r0_gantt"), f"{event_type} missing left gantt"
    assert ir.get("r2_gantt"), f"{event_type} missing r2_gantt"
    ig = data.get("impact_gantt") or {}
    assert ig.get("r1") or ig.get("r0")
    assert ig.get("r2")
    if event_type == "planned_downtime":
        layers = ir.get("gantt_layers") or {}
        assert layers.get("downtime_windows") or layers.get("breakdown_window")
    if event_type == "machine_breakdown":
        layers = ir.get("gantt_layers") or {}
        assert layers.get("breakdown_window")
