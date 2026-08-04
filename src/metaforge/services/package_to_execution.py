from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from metaforge.services.production_execution import start_execution


def _resolve_recommended_id(package: dict) -> str | None:
    evaluation = package.get("evaluation") or {}
    return package.get("recommended_schedule_id") or evaluation.get("recommended_schedule_id")


def _resolve_candidates(package: dict) -> list:
    evaluation = package.get("evaluation") or {}
    return (
        evaluation.get("candidates")
        or package.get("candidates")
        or package.get("candidate_schedules")
        or []
    )


def _match_candidate(candidates: list, recommended_id: str) -> dict | None:
    for candidate in candidates:
        for key in ("schedule_id", "solver", "id"):
            if candidate.get(key) == recommended_id:
                return candidate
    return None


def _solver_id_from_candidate(candidate: dict, recommended_id: str) -> str:
    return (
        candidate.get("solver")
        or candidate.get("schedule_id")
        or candidate.get("id")
        or recommended_id
    )


def extract_recommended_gantt(
    *, package: dict | None = None, candidates: list | None = None
) -> tuple[str, list]:
    """Extract solver id and gantt_data for the recommended schedule from a planning package."""
    package = package or {}

    recommended_id = _resolve_recommended_id(package)
    if not recommended_id:
        raise ValueError("no recommended schedule id in package")

    resolved_candidates = candidates if candidates is not None else _resolve_candidates(package)
    candidate = _match_candidate(resolved_candidates, recommended_id)
    if candidate is None:
        raise ValueError(f"recommended schedule {recommended_id!r} not found in candidates")

    gantt_data = candidate.get("gantt_data")
    if not gantt_data:
        raise ValueError(f"recommended schedule {recommended_id!r} has no gantt_data")

    return _solver_id_from_candidate(candidate, recommended_id), list(gantt_data)


_SOLVER_NAMES = {
    "ts": "禁忌搜索 TS",
    "ga": "遗传算法 GA",
    "sa": "模拟退火 SA",
    "aco": "蚁群 ACO",
    "edd": "最早交期 EDD",
    "spt": "最短加工 SPT",
    "mwkr": "剩余最多 MWKR",
    "fifo": "先进先出 FIFO",
}


def _schedule_snapshot(
    solver_id: str,
    gantt: list,
    *,
    metrics: dict | None = None,
    candidate: dict | None = None,
) -> dict:
    metrics = dict(metrics or (candidate or {}).get("metrics") or {})
    makespan = metrics.get("makespan")
    entry = {
        "id": solver_id,
        "algorithm": solver_id,
        "name": _SOLVER_NAMES.get(str(solver_id).lower(), str(solver_id).upper()),
        "gantt_data": list(gantt),
        "metrics": metrics,
        "best_score": makespan,
        "makespan": makespan,
    }
    return {solver_id: entry}


async def start_from_package(
    execution_coll,
    orders_coll,
    *,
    package: dict | None = None,
    run_id: str | None = None,
    plan_id: str | None = None,
    persist_plan: bool = True,
    sim_speed: float = 60.0,
    jobs: list | None = None,
    plan_name: str = "Package 推荐计划",
    candidates: list | None = None,
) -> dict:
    """Write recommended package gantt onto a plan, then start MES execution."""
    from bson import ObjectId

    resolved_package = dict(package or {})
    resolved_candidates = candidates

    if run_id:
        from metaforge.strategy.run_state import get_run

        run = get_run(run_id)
        if run:
            if not resolved_package:
                resolved_package = dict(run.get("package") or {})
            if resolved_candidates is None:
                resolved_candidates = run.get("candidate_schedules") or []
        elif not resolved_package and resolved_candidates is None:
            raise ValueError(f"run not found: {run_id!r}")
        # run 丢失但 body 已带 package/candidates 时继续（进程重启常见）

    solver_id, gantt = extract_recommended_gantt(
        package=resolved_package,
        candidates=resolved_candidates,
    )
    matched = _match_candidate(resolved_candidates or [], solver_id)
    schedule_result = _schedule_snapshot(
        solver_id,
        gantt,
        candidate=matched,
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    package_code = (
        resolved_package.get("package_code")
        or (plan_name.split(" · ", 1)[0] if plan_name else None)
        or f"PKG-{solver_id.upper()}"
    )

    if plan_id:
        oid = ObjectId(plan_id)
        sets: dict[str, Any] = {
            "schedule_result": schedule_result,
            "schedule_results": schedule_result,
            "updated_at": now_iso,
            "package_code": package_code,
            "recommended_solver": solver_id,
            "source": "package_to_execution",
        }
        if jobs is not None:
            sets["jobs"] = jobs
        if plan_name:
            sets["plan_name"] = plan_name
        if run_id:
            sets["source_run_id"] = run_id
        await orders_coll.update_one({"_id": oid}, {"$set": sets})
        resolved_plan_id = str(plan_id)
    elif persist_plan:
        doc = {
            "plan_name": plan_name,
            "package_code": package_code,
            "recommended_solver": solver_id,
            "jobs": jobs or [],
            "schedule_result": schedule_result,
            "schedule_results": schedule_result,
            "created_at": now_iso,
            "updated_at": now_iso,
            "status": "done",
            "source": "package_to_execution",
        }
        if run_id:
            doc["source_run_id"] = run_id
        result = await orders_coll.insert_one(doc)
        resolved_plan_id = str(result.inserted_id)
    else:
        raise ValueError("plan_id required when persist_plan=false")

    exec_doc = await start_execution(
        execution_coll,
        orders_coll,
        plan_id=resolved_plan_id,
        solver_id=solver_id,
        sim_speed=sim_speed,
    )
    return {
        **exec_doc,
        "plan_id": resolved_plan_id,
        "plan_name": plan_name,
        "package_code": package_code,
        "recommended_solver": solver_id,
    }
