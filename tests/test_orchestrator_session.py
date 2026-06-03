"""SessionStore 单测。"""

from metaforge.orchestrator.session import (
    apply_session_to_context,
    clear_all_sessions,
    create_session,
    get_artifacts,
    get_session,
    merge_artifacts,
    persist_after_run,
)


def setup_function():
    clear_all_sessions()


def teardown_function():
    clear_all_sessions()


def test_create_and_get_session():
    sid = create_session(initial_artifacts={"schedule_results": {"spt": {}}})
    s = get_session(sid)
    assert s is not None
    assert get_artifacts(sid)["schedule_results"]


def test_apply_session_merges_artifacts():
    sid = create_session(initial_artifacts={"interpretation": {"strategy_id": "delivery"}})
    ctx = apply_session_to_context(sid, {"artifacts": {"schedule_results": {"spt": {"ok": True}}}})
    assert ctx["artifacts"]["interpretation"]["strategy_id"] == "delivery"
    assert ctx["artifacts"]["schedule_results"]["spt"]["ok"] is True


def test_persist_after_run_creates_session_when_missing():
    sid = persist_after_run(
        None,
        agent_id="scheduling",
        request_context={"custom_data": [{"name": "J1"}]},
        response={"artifacts": {"schedule_results": {"spt": {}}}, "status": "success"},
    )
    assert get_session(sid)
    assert "schedule_results" in get_artifacts(sid)


def test_persist_after_run_updates_existing():
    sid = create_session()
    new_sid = persist_after_run(
        sid,
        agent_id="commitment",
        request_context={},
        response={"artifacts": {"delivery_assessment": {"overall": "met"}}},
    )
    assert new_sid == sid
    assert "delivery_assessment" in get_artifacts(sid)
