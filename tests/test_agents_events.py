"""events Agent 测试（collab 主路径）。"""

from metaforge.agents.base import AgentRequest
from metaforge.agents.events_collab_bridge import EventsCollabBridge
from metaforge.events_collab.pipeline import run_events
from metaforge.orchestrator.router import get_agent
from metaforge.tools.base import ToolContext, ToolResult
from metaforge.tools.load_all import load_all_tools


def setup_module():
    load_all_tools()


def _jobs():
    return [
        {
            "name": "工单A",
            "priority": 10,
            "due_date": 15.0,
            "tasks": [
                {"machine_id": 0, "duration": 3},
                {"machine_id": 1, "duration": 2},
            ],
        },
        {
            "name": "工单B",
            "priority": 20,
            "due_date": 20.0,
            "tasks": [
                {"machine_id": 1, "duration": 4},
                {"machine_id": 0, "duration": 2},
            ],
        },
    ]


def _ok(data, key=None):
    return ToolResult(ok=True, data=data, artifacts_key=key)


def test_events_default_reschedule_uses_fixed_pipeline_without_llm(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("LLM_PLAN_ENABLED", "1")
    calls = []

    def invoke(name, params, ctx: ToolContext):
        calls.append(name)
        scripts = {
            "execution.get_state": _ok({}, "execution_state"),
            "events.parse_event": _ok(
                {"event_type": "machine_breakdown", "params": {}},
                "event_envelope",
            ),
            "events.check_insert_job": _ok({"status": "ready"}, "insert_job_intake"),
            "events.reschedule": _ok(
                {"results": {}, "impact_report": {"delay_details": []}},
                "schedule_results",
            ),
            "delivery.compare_commitment": _ok({}, "commitment_delta"),
            "delivery.explain_impact": _ok({"summary_zh": "ok"}, "impact_summary"),
        }
        return scripts[name]

    out = run_events(message="3号机坏了4小时，帮我重排", invoke_tool=invoke)
    assert out["status"] == "success"
    assert calls[1] == "events.parse_event"
    assert out["artifacts"]["events_trace"]["stages"][0] == "get_state"
    agent = get_agent("events")
    assert isinstance(agent, EventsCollabBridge)


def test_events_insert_pending_uses_merge_not_parse():
    calls = []

    def invoke(name, params, ctx: ToolContext):
        calls.append(name)
        scripts = {
            "events.merge_insert_job": _ok(
                {
                    "status": "ready",
                    "draft": {
                        "name": "急单",
                        "tasks": [{"machine_id": 0, "duration": 1}],
                    },
                },
                "insert_job_intake",
            ),
            "events.check_insert_job": _ok(
                {
                    "status": "ready",
                    "draft": {
                        "name": "急单",
                        "tasks": [{"machine_id": 0, "duration": 1}],
                    },
                },
                "insert_job_intake",
            ),
            "events.reschedule": _ok(
                {"results": {}, "impact_report": {"delay_details": []}},
                "schedule_results",
            ),
            "delivery.explain_impact": _ok({"summary_zh": "插单完成"}, "impact_summary"),
        }
        return scripts[name]

    out = run_events(
        message="2道工序：3号机5h + 4号机3h",
        context={
            "artifacts": {
                "insert_job_intake": {
                    "status": "need_input",
                    "draft": {"name": "急单", "priority": 100, "tasks": []},
                },
                "event_envelope": {
                    "event_type": "insert_order",
                    "params": {
                        "freeze_time": 20.0,
                        "insert_job": {"name": "急单", "tasks": []},
                    },
                },
            }
        },
        invoke_tool=invoke,
    )
    assert out["status"] == "success"
    assert calls[0] == "events.merge_insert_job"
    assert "events.parse_event" not in calls


def test_events_agent_pipeline_has_reschedule_chain():
    calls = []

    def invoke(name, params, ctx: ToolContext):
        calls.append(name)
        scripts = {
            "execution.get_state": _ok({}, "execution_state"),
            "events.parse_event": _ok({"event_type": "priority_change"}, "event_envelope"),
            "events.check_insert_job": _ok({"status": "ready"}, "insert_job_intake"),
            "events.reschedule": _ok(
                {"results": {}, "impact_report": {}},
                "schedule_results",
            ),
            "delivery.compare_commitment": _ok({}, "commitment_delta"),
            "delivery.explain_impact": _ok({"summary_zh": "ok"}, "impact_summary"),
        }
        return scripts[name]

    out = run_events(message="工单A优先级调高", invoke_tool=invoke)
    assert "events.parse_event" in calls
    assert "events.reschedule" in calls
    assert "delivery.explain_impact" in calls
    assert out["status"] == "success"


def test_events_agent_run_skip_parse():
    agent = EventsCollabBridge()
    req = AgentRequest(
        params={
            "skip_parse": True,
            "event_envelope": {
                "event_type": "order_cancel",
                "base_jobs": _jobs(),
                "params": {"job_names": ["工单B"]},
                "reschedule_options": {"solvers": ["spt"]},
            },
        },
        context={"custom_data": _jobs()},
    )
    resp = agent.run(req)
    assert resp.status == "success"
    impact = resp.artifacts.get("impact_report", {})
    assert "delay_details" in impact
    assert "commitment_changes" in impact
    assert "events_trace" in resp.artifacts


def test_get_agent_events_returns_collab_bridge():
    assert isinstance(get_agent("events"), EventsCollabBridge)
