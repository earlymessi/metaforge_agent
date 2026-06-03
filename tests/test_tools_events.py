"""events Tool 测试。"""

from metaforge.tools.events.parse_event import parse_event_message
from metaforge.tools.load_all import load_all_tools
from metaforge.tools.registry import run_tool
from metaforge.tools.base import ToolContext


def setup_module():
    load_all_tools()


def _jobs():
    return [
        {
            "name": "工单A",
            "priority": 10,
            "tasks": [{"machine_id": 0, "duration": 2}],
        },
        {
            "name": "工单B",
            "priority": 20,
            "tasks": [{"machine_id": 1, "duration": 3}],
        },
    ]


def test_parse_insert_order():
    env = parse_event_message("紧急插单", base_jobs=_jobs())
    assert env["event_type"] == "insert_order"


def test_parse_machine_breakdown():
    env = parse_event_message("3号机坏了4小时", base_jobs=_jobs())
    assert env["event_type"] == "machine_breakdown"
    assert env["params"]["machine_id"] == 2
    assert env["params"]["breakdown_duration"] == 4.0


def test_parse_planned_downtime():
    env = parse_event_message("1号机停机大修8小时", base_jobs=_jobs())
    assert env["event_type"] == "planned_downtime"
    assert env["params"]["downtime_blocks"]


def test_parse_priority_change():
    env = parse_event_message("工单A加急", base_jobs=_jobs())
    assert env["event_type"] == "priority_change"
    assert env["params"]["changes"][0]["new_priority"] == 100


def test_parse_due_date_change_order_name():
    env = parse_event_message("订单106交期改为20", base_jobs=_jobs())
    assert env["event_type"] == "due_date_change"
    changes = env["params"]["due_date_changes"]
    assert len(changes) == 1
    assert changes[0]["job_name"] == "订单106"
    assert changes[0]["new_due_date"] == 20.0


def test_events_reschedule_priority_change():
    ctx = ToolContext(custom_data=_jobs())
    ctx.artifacts["event_envelope"] = {
        "event_type": "priority_change",
        "base_jobs": _jobs(),
        "params": {"changes": [{"job_name": "工单A", "new_priority": 100}]},
        "reschedule_options": {"solvers": ["spt"]},
    }
    r = run_tool("events.reschedule", {}, ctx)
    assert r.ok, r.error
    impact = ctx.artifacts.get("impact_report") or r.data.get("impact_report")
    assert impact is not None
    assert "delay_details" in impact
    assert "commitment_changes" in impact
