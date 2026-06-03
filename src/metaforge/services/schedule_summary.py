"""从 schedule_results 生成轻量摘要（SSE / 对话展示）。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from metaforge.services.persist_store import _pick_best_schedule


def normalize_schedule_results(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        return {}
    if "results" in raw and not any(
        k in raw for k in ("spt", "edd", "ts", "ga", "aco", "sa", "ppo")
    ):
        inner = raw.get("results")
        if isinstance(inner, dict):
            return inner
    # 单算法快照：顶层含 gantt_data，键名是字段而非 solver id
    if "gantt_data" in raw and not any(
        isinstance(v, dict) and "gantt_data" in v for v in raw.values() if isinstance(v, dict)
    ):
        sid = str(raw.get("id") or raw.get("algorithm") or "saved")
        return {sid: raw}
    return raw


def resolve_plan_schedule_map(order_doc: Any) -> Dict[str, Any]:
    """从计划文档合并 schedule_results（优先）与 schedule_result 单份快照。"""
    if not order_doc or not isinstance(order_doc, dict):
        return {}
    multi = order_doc.get("schedule_results")
    if isinstance(multi, dict) and multi:
        norm = normalize_schedule_results(multi)
        if norm:
            return norm
    single = order_doc.get("schedule_result")
    if isinstance(single, dict) and single:
        return normalize_schedule_results(single)
    return {}


def build_schedule_summary(schedule_results: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sr = normalize_schedule_results(schedule_results)
    if not sr:
        return None
    best_sid, best = _pick_best_schedule(sr)
    if not best_sid:
        return None
    ok_count = sum(1 for v in sr.values() if isinstance(v, dict) and not v.get("error"))
    return {
        "best_solver_id": best_sid,
        "best_solver_name": best.get("name") or best_sid,
        "makespan": best.get("best_score"),
        "solver_count": ok_count,
        "solver_ids": [k for k, v in sr.items() if isinstance(v, dict) and not v.get("error")],
    }
