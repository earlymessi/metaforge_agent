"""MES production_execution 服务测试。"""

from datetime import datetime, timedelta, timezone

from metaforge.services.production_execution import (
    build_execution_doc,
    compute_sim_time,
    extract_solver_result,
    gantt_makespan,
    resolve_solver_entry,
)
from metaforge.services.schedule_summary import resolve_plan_schedule_map


def test_compute_sim_time_one_minute_equals_one_hour():
    started = datetime.now(timezone.utc) - timedelta(seconds=60)
    t = compute_sim_time(
        started_at_wall=started.isoformat(),
        sim_speed=60.0,
        makespan=100.0,
        status="running",
        paused_accum_sec=0.0,
    )
    assert 0.9 <= t <= 1.1


def test_compute_sim_time_caps_at_makespan():
    started = datetime.now(timezone.utc) - timedelta(hours=2)
    t = compute_sim_time(
        started_at_wall=started.isoformat(),
        sim_speed=60.0,
        makespan=10.0,
        status="running",
        paused_accum_sec=0.0,
    )
    assert t == 10.0


def test_compute_sim_time_paused_holds():
    started = datetime.now(timezone.utc) - timedelta(hours=1)
    t = compute_sim_time(
        started_at_wall=started.isoformat(),
        sim_speed=60.0,
        makespan=100.0,
        status="paused",
        paused_accum_sec=0.0,
        sim_time_frozen=5.0,
    )
    assert t == 5.0


def test_extract_solver_result_flat():
    sr = {"ts": {"gantt_data": [{"job_id": 0}], "best_score": 44, "metrics": {}}}
    entry = extract_solver_result(sr, "ts")
    assert entry["gantt_data"][0]["job_id"] == 0


def test_extract_solver_result_nested_results():
    sr = {"results": {"ga": {"gantt_data": [{"job_id": 1}], "best_score": 40}}}
    entry = extract_solver_result(sr, "ga")
    assert entry["gantt_data"][0]["job_id"] == 1


def test_gantt_makespan():
    gantt = [{"end": 10}, {"end": 44.5}]
    assert gantt_makespan(gantt) == 44.5


def test_resolve_plan_schedule_map_prefers_multi():
    order = {
        "schedule_results": {"ts": {"gantt_data": [{"end": 10}]}},
        "schedule_result": {"algorithm": "Tabu Search", "gantt_data": [{"end": 99}]},
    }
    m = resolve_plan_schedule_map(order)
    assert "ts" in m
    assert m["ts"]["gantt_data"][0]["end"] == 10


def test_build_execution_doc_uses_schedule_results():
    order = {
        "_id": "plan1",
        "plan_name": "demo",
        "jobs": [{"name": "J1", "tasks": []}],
        "schedule_results": {"ts": {"gantt_data": [{"end": 12}], "best_score": 12}},
        "schedule_result": {"algorithm": "Tabu Search", "gantt_data": [{"end": 99}]},
    }
    doc = build_execution_doc(order, "ts")
    assert doc["baseline_solver"] == "ts"
    assert doc["makespan"] == 12.0


def test_resolve_solver_entry_single_fallback():
    sr = {"Tabu Search": {"gantt_data": [{"end": 5}], "best_score": 5}}
    sid, entry = resolve_solver_entry(sr, "ts")
    assert sid == "ts"
    assert entry["best_score"] == 5


def test_resolve_solver_entry_chinese_display_name():
    sr = {"模拟退火": {"gantt_data": [{"end": 8}], "best_score": 8}}
    sid, entry = resolve_solver_entry(sr, "模拟退火")
    assert sid == "sa"
    assert entry["best_score"] == 8
