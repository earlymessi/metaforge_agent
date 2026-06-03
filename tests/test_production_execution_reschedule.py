"""MES 执行态在事件重排后更新基准甘特。"""

import asyncio

from metaforge.services.production_execution import ACTIVE_ID, apply_reschedule_to_execution, gantt_makespan


class _FakeColl:
    def __init__(self, doc):
        self.doc = doc

    async def find_one(self, query):
        if query.get("_id") == ACTIVE_ID:
            return dict(self.doc)
        return None

    async def replace_one(self, query, doc, upsert=False):
        self.doc = dict(doc)


def test_apply_reschedule_updates_baseline_gantt():
    g0 = [
        {"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0, "end": 5},
    ]
    coll = _FakeColl(
        {
            "_id": ACTIVE_ID,
            "status": "paused",
            "sim_time": 2.0,
            "sim_time_frozen": 2.0,
            "makespan": 5.0,
            "baseline_gantt": g0,
            "jobs_snapshot": [{"name": "J1"}],
        }
    )
    g1 = g0 + [
        {"job_id": 1, "machine_id": 0, "operation_id": 0, "start": 5, "end": 10, "job_name": "急单"},
    ]
    jobs = [{"name": "J1"}, {"name": "急单", "tasks": []}]
    impact_summary = {
        "summary_zh": "插单影响",
        "impact_report": {
            "event_type": "insert_order",
            "affected_jobs": 2,
            "r0_gantt": g0,
            "r1_gantt": g0,
            "r2_gantt": g1,
        },
        "event_type": "insert_order",
        "rescheduled_at": "2026-05-30T00:00:00+00:00",
    }
    results = {"ts": {"gantt_data": g1, "best_score": 10.0}}

    async def _run():
        out = await apply_reschedule_to_execution(
            coll,
            gantt=g1,
            jobs_snapshot=jobs,
            solver_id="ts",
            impact_summary=impact_summary,
            reschedule_results=results,
        )
        assert out is not None
        assert len(out["baseline_gantt"]) == 2
        assert out["makespan"] == gantt_makespan(g1)
        assert len(out["jobs_snapshot"]) == 2
        assert out["last_impact_summary"]["event_type"] == "insert_order"
        assert out["last_impact_gantt"]["r2"] == g1
        assert out["last_reschedule_results"]["ts"]["gantt_data"]

    asyncio.run(_run())
