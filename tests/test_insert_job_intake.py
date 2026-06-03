"""插单多轮补全 intake 逻辑。"""

from metaforge.events.insert_job_intake import (
    assess_insert_order_envelope,
    merge_insert_job_followup,
    parse_insert_job_name,
    validate_insert_job,
)
from metaforge.orchestrator.router import has_pending_insert_job_intake, resolve_agent_route


def test_parse_insert_job_name_from_new_order():
    assert parse_insert_job_name("9h新增订单a，帮我重排") == "a"


def test_message_looks_like_insert_order():
    from metaforge.events.insert_job_intake import message_looks_like_insert_order

    assert message_looks_like_insert_order("40h插入订单，两道工序，三号机2h，四号机4h")
    assert not message_looks_like_insert_order("工单A交期改为50")


def test_parse_event_message_insert_with_two_ops():
    from metaforge.tools.events.parse_event import parse_event_message

    env = parse_event_message("40h插入订单，两道工序，三号机2h，四号机4h")
    assert env["event_type"] == "insert_order"
    assert env["params"]["freeze_time"] == 40.0
    tasks = env["params"]["insert_job"]["tasks"]
    assert len(tasks) == 2
    assert tasks[0]["machine_id"] == 2
    assert tasks[0]["duration"] == 2.0
    assert tasks[1]["machine_id"] == 3
    assert tasks[1]["duration"] == 4.0


def test_insert_order_missing_tasks_need_input():
    env = {
        "event_type": "insert_order",
        "params": {
            "mode": "global",
            "freeze_time": 9.0,
            "insert_job": {"name": "a", "priority": 100, "tasks": []},
        },
        "summary_zh": "9小时后新增订单a",
    }
    intake = assess_insert_order_envelope(env, original_message="9h新增订单a")
    assert intake["status"] == "need_input"
    assert "tasks" in intake["missing_fields"]
    assert "a" in intake["question_zh"]


def test_merge_followup_completes_job():
    draft = {"name": "a", "priority": 100, "tasks": []}
    merged = merge_insert_job_followup("3号机5小时，优先级100", draft, use_llm=False)
    ok, missing = validate_insert_job(merged)
    assert ok, missing
    assert merged["tasks"][0]["machine_id"] == 2
    assert merged["tasks"][0]["duration"] == 5.0


def test_confirm_default_stub():
    draft = {"name": "a", "tasks": []}
    merged = merge_insert_job_followup("确认默认工艺", draft, use_llm=False)
    ok, missing = validate_insert_job(merged, allow_stub=merged.get("_user_confirmed_stub"))
    assert ok, missing


def test_router_followup_message_without_session():
    from metaforge.orchestrator.router import resolve_agent_route

    route = resolve_agent_route("2道工序：3号机5h + 4号机3h")
    assert route["agent_id"] == "events"
    assert "补充" in (route.get("rule_reason_zh") or "")


def test_router_session_continue_overrides_scheduling_fallback():
    ctx = {"artifacts": {"insert_job_intake": {"status": "need_input", "draft": {"name": "a"}}}}
    route = resolve_agent_route("随便说一句", context=ctx)
    assert route["agent_id"] == "events"
    assert route["router"] == "session_continue"


def test_merge_two_ops_followup():
    draft = {"name": "a", "priority": 100, "tasks": []}
    merged = merge_insert_job_followup("2道工序：3号机5h + 4号机3h", draft, use_llm=False)
    ok, missing = validate_insert_job(merged)
    assert ok, missing
    assert len(merged["tasks"]) == 2
    assert merged["tasks"][0]["duration"] == 5.0
    assert merged["tasks"][1]["duration"] == 3.0


def test_resolve_route_phase_continues_intake():
    from metaforge.orchestrator.preview import resolve_route_phase

    ctx = {"artifacts": {"insert_job_intake": {"status": "need_input", "draft": {"name": "a"}}}}
    route = resolve_route_phase("2道工序：3号机5h + 4号机3h", context=ctx)
    assert route["agent_id"] == "events"
    assert route["router"] == "session_continue"
