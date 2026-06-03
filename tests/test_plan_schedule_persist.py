"""计划排程结果写入 Mongo。"""

import pytest

from metaforge.services import plan_store
from metaforge.services.plan_schedule import save_schedule_results


@pytest.fixture
def plan_coll():
    try:
        import mongomock
    except ImportError:
        pytest.skip("mongomock not installed")
    coll = mongomock.MongoClient().db.work_orders
    plan_store.configure_plan_store(coll)
    yield coll
    plan_store.configure_plan_store(None)


def test_save_schedule_results_multi_solver(plan_coll):
    doc, err = plan_store.create_plan(plan_name="sched-test", jobs=[])
    assert not err
    pid = doc["id"]
    results = {
        "spt": {"id": "spt", "name": "SPT", "best_score": 42.0, "score": 1.0, "gantt_data": []},
        "ts": {"id": "ts", "name": "Tabu", "best_score": 40.0, "score": 0.9, "gantt_data": []},
    }
    updated, err2 = save_schedule_results(pid, results)
    assert not err2
    assert updated.get("schedule_results")
    assert updated["schedule_result"]["best_score"] == 40.0
    assert updated.get("status") == "done"


def test_save_schedule_results_with_jobs(plan_coll):
    doc, err = plan_store.create_plan(plan_name="jobs-test", jobs=[{"name": "J1", "tasks": []}])
    assert not err
    pid = doc["id"]
    results = {
        "spt": {"id": "spt", "name": "SPT", "best_score": 42.0, "score": 1.0, "gantt_data": []},
    }
    new_jobs = [{"name": "J1", "due_date": 20.0, "tasks": []}, {"name": "急单", "tasks": []}]
    updated, err2 = save_schedule_results(pid, results, jobs=new_jobs)
    assert not err2
    assert len(updated.get("jobs") or []) == 2
    assert updated["jobs"][0]["due_date"] == 20.0


def test_persist_schedule_with_hitl_auto_save_when_empty(plan_coll):
    from metaforge.services.plan_schedule import persist_schedule_with_hitl

    doc, err = plan_store.create_plan(plan_name="new-plan", jobs=[{"name": "J1", "tasks": []}])
    assert not err
    pid = doc["id"]
    results = {"spt": {"id": "spt", "best_score": 10.0, "metrics": {"makespan": 12.0}, "gantt_data": []}}
    kind, payload = persist_schedule_with_hitl(pid, results)
    assert kind == "saved"
    assert payload["plan_id"] == pid


def test_persist_schedule_with_hitl_pending_when_overwrite(plan_coll):
    from metaforge.services import persist_store
    from metaforge.services.plan_schedule import persist_schedule_with_hitl, save_schedule_results

    persist_store.clear_pending_store()
    doc, err = plan_store.create_plan(plan_name="old-plan", jobs=[{"name": "J1", "tasks": []}])
    assert not err
    pid = doc["id"]
    old_results = {"ts": {"id": "ts", "best_score": 50.0, "metrics": {"makespan": 50.0}, "gantt_data": []}}
    save_schedule_results(pid, old_results)

    new_results = {"spt": {"id": "spt", "best_score": 40.0, "metrics": {"makespan": 40.0}, "gantt_data": []}}
    new_jobs = [{"name": "J1", "due_date": 25.0, "tasks": []}]
    kind, payload = persist_schedule_with_hitl(
        pid, new_results, jobs=new_jobs, impact_summary={"summary_zh": "重排影响"}
    )
    assert kind == "pending"
    assert payload["confirm_token"]
    assert payload["preview"]["has_existing_schedule"] is True
    assert payload["preview"]["previous_makespan"] == 50.0
    assert payload["preview"]["jobs_update_count"] == 1
    persist_store.clear_pending_store()


def test_build_impact_summary_payload():
    from metaforge.services.plan_schedule import build_impact_summary_payload

    payload = build_impact_summary_payload(
        {"event_type": "insert_order", "summary_zh": "插单", "affected_jobs": 1}
    )
    assert payload["event_type"] == "insert_order"
    assert payload["impact_report"]["affected_jobs"] == 1
    assert payload["rescheduled_at"]
