"""扩展事件 REST / dispatch 测试。"""

import pytest

from metaforge.services.event_reschedule import dispatch_event_reschedule


def _jobs():
    return [
        {
            "name": "工单A",
            "priority": 10,
            "due_date": 18.0,
            "tasks": [
                {"machine_id": 0, "duration": 3},
                {"machine_id": 1, "duration": 2},
            ],
        },
        {
            "name": "工单B",
            "priority": 20,
            "due_date": 22.0,
            "tasks": [
                {"machine_id": 1, "duration": 4},
                {"machine_id": 0, "duration": 2},
            ],
        },
    ]


def _opts():
    return {"solvers": ["spt"], "random_seed": 1}


def _assert_success(raw):
    assert "error" not in raw, raw.get("error")
    data = raw["data"]
    assert data["results"]
    assert "delay_details" in data["impact_report"]
    assert "commitment_changes" in data["impact_report"]


@pytest.mark.parametrize(
    "event_type,params",
    [
        (
            "planned_downtime",
            {"downtime_blocks": [{"machine_id": 0, "start": 0.0, "end": 5.0, "label": "maint"}]},
        ),
        ("material_delay", {"job_name": "工单A", "delay_hours": 4.0}),
        ("priority_change", {"changes": [{"job_name": "工单A", "new_priority": 100}]}),
        ("order_cancel", {"job_names": ["工单B"]}),
        ("quantity_change", {"changes": [{"job_name": "工单A", "new_quantity": 2}]}),
    ],
)
def test_dispatch_extended_events(event_type, params):
    raw = dispatch_event_reschedule(
        {
            "event_type": event_type,
            "base_jobs": _jobs(),
            "params": params,
            "reschedule_options": _opts(),
        }
    )
    _assert_success(raw)


def test_extended_event_routes_registered():
    from main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    for p in (
        "/api/events/planned_downtime",
        "/api/events/material_delay",
        "/api/events/priority_change",
        "/api/events/order_cancel",
        "/api/events/quantity_change",
        "/api/agents/kitting/run",
        "/api/agents/events/run",
    ):
        assert p in paths, f"missing route {p}"
