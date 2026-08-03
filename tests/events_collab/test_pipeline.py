from __future__ import annotations

from typing import Any, Dict, List

from metaforge.events_collab.pipeline import run_events
from metaforge.tools.base import ToolContext, ToolResult


def _ok(data: Dict[str, Any], key: str | None = None) -> ToolResult:
    return ToolResult(ok=True, data=data, artifacts_key=key)


def _fail(err: str) -> ToolResult:
    return ToolResult(ok=False, data={}, error=err)


class _ScriptedInvoke:
    def __init__(self, scripts: Dict[str, ToolResult]):
        self.scripts = scripts
        self.calls: List[str] = []

    def __call__(self, name: str, params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        self.calls.append(name)
        if name not in self.scripts:
            return _fail(f"unexpected tool: {name}")
        return self.scripts[name]


def test_catalog_short_path_only_lists_types():
    invoke = _ScriptedInvoke(
        {
            "events.list_event_types": _ok(
                {
                    "event_types": [
                        {"name_zh": "设备故障"},
                        {"name_zh": "插单"},
                    ]
                },
                "event_type_catalog",
            )
        }
    )
    out = run_events(message="支持哪些事件类型？", invoke_tool=invoke)
    assert out["status"] == "success"
    assert invoke.calls == ["events.list_event_types"]
    assert out["artifacts"]["events_trace"]["stages"] == ["catalog"]
    assert "设备故障" in out["summary_zh"]


def test_skip_parse_envelope_calls_reschedule():
    invoke = _ScriptedInvoke(
        {
            "execution.get_state": _ok({"status": "idle"}, "execution_state"),
            "events.check_insert_job": _ok({"status": "ready"}, "insert_job_intake"),
            "events.reschedule": _ok(
                {
                    "results": {"spt": {"makespan": 10}},
                    "impact_report": {"delay_details": []},
                    "event_type": "order_cancel",
                },
                "schedule_results",
            ),
            "delivery.compare_commitment": _ok({"ok": True}, "commitment_delta"),
            "delivery.explain_impact": _ok(
                {"summary_zh": "取消订单影响已说明。"},
                "impact_summary",
            ),
        }
    )
    out = run_events(
        message="",
        params={
            "skip_parse": True,
            "event_envelope": {
                "event_type": "order_cancel",
                "params": {"job_names": ["工单B"]},
            },
        },
        invoke_tool=invoke,
    )
    assert out["status"] == "success"
    assert "events.parse_event" not in invoke.calls
    assert "events.reschedule" in invoke.calls
    tools = [x["tool"] for x in out["artifacts"]["events_trace"]["tool_log"]]
    assert "events.reschedule" in tools
    assert out["events_trace"]["status"] == "success"


def test_need_input_does_not_reschedule():
    invoke = _ScriptedInvoke(
        {
            "execution.get_state": _ok({}, "execution_state"),
            "events.parse_event": _ok(
                {
                    "event_type": "insert_order",
                    "params": {"insert_job": {"name": "急单", "tasks": []}},
                },
                "event_envelope",
            ),
            "events.check_insert_job": _ok(
                {
                    "status": "need_input",
                    "question_zh": "请补充工序",
                    "missing_fields": ["tasks"],
                    "draft": {"name": "急单"},
                },
                "insert_job_intake",
            ),
        }
    )
    out = run_events(message="插一个急单", invoke_tool=invoke)
    assert out["status"] == "need_input"
    assert "events.reschedule" not in invoke.calls
    assert out["pending_action"]["type"] == "insert_job_details"
    assert out["artifacts"]["events_trace"]["status"] == "need_input"
