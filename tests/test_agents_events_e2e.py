"""异常重排 Agent API 端到端（TestClient）。"""

import pytest
from fastapi.testclient import TestClient

from metaforge.tools.load_all import load_all_tools


def _jobs():
    return [
        {
            "name": "工单A",
            "priority": 10,
            "due_date": 30.0,
            "tasks": [
                {"machine_id": 0, "duration": 5},
                {"machine_id": 1, "duration": 3},
            ],
        },
        {
            "name": "工单B",
            "priority": 10,
            "due_date": 40.0,
            "tasks": [
                {"machine_id": 1, "duration": 4},
                {"machine_id": 0, "duration": 2},
            ],
        },
    ]


def _baseline_gantt():
    return [
        {"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0.0, "end": 5.0, "job_name": "工单A"},
        {"job_id": 0, "machine_id": 1, "operation_id": 1, "start": 5.0, "end": 8.0, "job_name": "工单A"},
        {"job_id": 1, "machine_id": 1, "operation_id": 0, "start": 8.0, "end": 12.0, "job_name": "工单B"},
        {"job_id": 1, "machine_id": 0, "operation_id": 1, "start": 12.0, "end": 14.0, "job_name": "工单B"},
    ]


@pytest.fixture(scope="module")
def client():
    load_all_tools()
    from main import app

    with TestClient(app) as c:
        yield c


def test_events_agent_list_types(client):
    r = client.post(
        "/api/agents/events/run",
        json={"message": "支持哪些异常事件类型", "custom_data": _jobs()},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "success"
    assert data.get("agent") == "events"
    catalog = data.get("artifacts", {}).get("event_type_catalog", {})
    types = {e.get("event_type") for e in catalog.get("event_types", [])}
    assert "insert_order" in types
    assert "machine_breakdown" in types
    assert "due_date_change" in types


def test_events_agent_insert_order_dual_gantt(client):
    r = client.post(
        "/api/agents/events/run",
        json={
            "message": "",
            "custom_data": _jobs(),
            "params": {
                "skip_parse": True,
                "event_envelope": {
                    "event_type": "insert_order",
                    "base_jobs": _jobs(),
                    "params": {
                        "insert_job": {
                            "name": "急单",
                            "priority": 100,
                            "tasks": [{"name": "X", "machine_id": 0, "duration": 4}],
                        },
                        "freeze_time": 0.0,
                        "mode": "local_repair",
                    },
                    "reschedule_options": {
                        "solvers": ["spt"],
                        "baseline_gantt": _baseline_gantt(),
                        "baseline_solver": "spt",
                    },
                },
            },
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "success", data.get("error")
    impact = data.get("artifacts", {}).get("impact_report", {})
    assert impact.get("event_type") == "insert_order"
    assert len(impact.get("r1_gantt") or []) > 0
    assert len(impact.get("r2_gantt") or []) > 0
    assert impact.get("scenarios", {}).get("r1", {}).get("label")


def test_events_agent_due_date_dual_gantt(client):
    r = client.post(
        "/api/agents/events/run",
        json={
            "message": "",
            "custom_data": _jobs(),
            "params": {
                "skip_parse": True,
                "event_envelope": {
                    "event_type": "due_date_change",
                    "base_jobs": _jobs(),
                    "params": {
                        "due_date_changes": [{"job_name": "工单A", "new_due_date": 50.0}],
                    },
                    "reschedule_options": {
                        "solvers": ["spt"],
                        "baseline_gantt": _baseline_gantt(),
                        "baseline_solver": "spt",
                    },
                },
            },
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "success", data.get("error")
    impact = data.get("artifacts", {}).get("impact_report", {})
    assert impact.get("event_type") == "due_date_change"
    assert len(impact.get("r1_gantt") or []) > 0
    assert len(impact.get("r2_gantt") or []) > 0


def test_events_agent_parse_breakdown_message(client):
    r = client.post(
        "/api/agents/events/run",
        json={
            "message": "3号机坏了4小时，请重排",
            "custom_data": _jobs(),
            "params": {
                "event_envelope": {
                    "event_type": "machine_breakdown",
                    "base_jobs": _jobs(),
                    "params": {
                        "machine_id": 0,
                        "breakdown_start": 2.0,
                        "breakdown_duration": 4.0,
                        "freeze_time": 2.0,
                    },
                    "reschedule_options": {
                        "solvers": ["spt"],
                        "baseline_gantt": _baseline_gantt(),
                        "baseline_solver": "spt",
                    },
                },
                "skip_parse": True,
            },
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "success", data.get("error")
    impact = data.get("artifacts", {}).get("impact_report", {})
    assert impact.get("event_type") == "machine_breakdown"
    assert len(impact.get("r1_gantt") or []) > 0
    assert len(impact.get("r2_gantt") or []) > 0
    assert data.get("summary_zh")
