"""新增 Tool 单测。"""

from metaforge.tools.base import ToolContext
from metaforge.tools.load_all import load_all_tools
from metaforge.tools.registry import list_tools, run_tool


def setup_module():
    load_all_tools()


def test_tool_registry_count_at_least_25():
    names = [t["name"] for t in list_tools()]
    assert len(names) >= 25
    for required in (
        "material.compute_delays",
        "events.list_event_types",
        "scheduling.list_catalog",
        "delivery.compare_commitment",
        "data.rename_plan",
        "data.duplicate_plan",
        "data.update_status",
    ):
        assert required in names


def test_scheduling_list_catalog():
    ctx = ToolContext()
    r = run_tool("scheduling.list_catalog", {}, ctx)
    assert r.ok
    assert len(r.data.get("strategies", [])) >= 2
    assert len(r.data.get("solvers", [])) >= 5


def test_events_list_event_types():
    ctx = ToolContext()
    r = run_tool("events.list_event_types", {}, ctx)
    assert r.ok
    assert r.data.get("count", 0) >= 8


def test_material_compute_delays():
    jobs = [
        {
            "name": "工单B",
            "priority": 5,
            "bom": [{"material_id": "MAT_X", "quantity_per_unit": 10}],
            "tasks": [{"machine_id": 0, "duration": 3}],
        },
        {
            "name": "工单A",
            "priority": 10,
            "bom": [{"material_id": "MAT_X", "quantity_per_unit": 5}],
            "tasks": [{"machine_id": 0, "duration": 2}],
        },
    ]
    ctx = ToolContext(custom_data=jobs, extras={"inventory": {"MAT_X": 6.0}})
    r = run_tool("material.compute_delays", {}, ctx)
    assert r.ok
    assert r.data.get("jobs_with_delay", 0) >= 1


def test_delivery_compare_commitment():
    ctx = ToolContext(
        artifacts={
            "impact_report": {
                "commitment_changes": [
                    {
                        "job_name": "J1",
                        "delta": 2.0,
                        "old_risk_level": "low",
                        "new_risk_level": "high",
                    }
                ]
            }
        }
    )
    r = run_tool("delivery.compare_commitment", {}, ctx)
    assert r.ok
    assert r.data.get("worsened_count") == 1
