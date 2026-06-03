"""计划排程结果持久化（MongoDB work_orders）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from metaforge.services.persist_store import _pick_best_schedule, propose_persist
from metaforge.services import plan_store
from metaforge.utils.bson_safe import to_bson_safe


def plan_has_saved_schedule(plan_doc: Optional[Dict[str, Any]]) -> bool:
    """计划是否已有可覆盖的排程快照。"""
    if not plan_doc:
        return False
    sr = plan_doc.get("schedule_results")
    if isinstance(sr, dict) and sr:
        return True
    if plan_doc.get("schedule_result"):
        return True
    return False


def _previous_schedule_preview(plan_doc: Dict[str, Any]) -> Dict[str, Any]:
    sr = plan_doc.get("schedule_result") or {}
    if not sr and isinstance(plan_doc.get("schedule_results"), dict):
        _, sr = _pick_best_schedule(plan_doc["schedule_results"])
    metrics = sr.get("metrics") or {}
    return {
        "best_solver": sr.get("id") or sr.get("name"),
        "makespan": metrics.get("makespan") or sr.get("best_score") or sr.get("makespan"),
        "best_score": sr.get("best_score"),
    }


def persist_schedule_with_hitl(
    plan_id: str,
    schedule_results: Dict[str, Any],
    *,
    interpretation: Optional[Dict[str, Any]] = None,
    delivery_assessment: Optional[Dict[str, Any]] = None,
    impact_summary: Optional[Dict[str, Any]] = None,
    jobs: Optional[List[Any]] = None,
    plan_name: Optional[str] = None,
    status: str = "done",
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    落库策略：计划尚无排程则直接写入；已有排程则 HITL propose，返回 pending_action。

    Returns:
        ("saved", {"plan_id": ...}) | ("pending", pending_action) | ("error", {"error": ...})
    """
    if not plan_id or not schedule_results:
        return "error", {"error": "plan_id and schedule_results required"}

    existing, err = plan_store.get_plan(str(plan_id))
    if err and err != "plan_store not configured":
        return "error", {"error": err}

    resolved_name = plan_name or (existing or {}).get("plan_name") or str(plan_id)
    best_sid, best_entry = _pick_best_schedule(schedule_results)

    if existing and plan_has_saved_schedule(existing):
        prev = _previous_schedule_preview(existing)
        token_data = propose_persist(
            plan_id=str(plan_id),
            schedule_result=best_entry,
            schedule_results=schedule_results,
            delivery_assessment=delivery_assessment,
            plan_name=resolved_name,
            interpretation=interpretation,
            jobs=jobs,
            impact_summary=impact_summary,
            has_existing_schedule=True,
            previous_schedule=prev,
            persist_status=status,
        )
        preview = token_data.get("preview") or {}
        summary_zh = (
            f"计划「{preview.get('plan_name', resolved_name)}」已有排程"
            f"（makespan={preview.get('previous_makespan', '—')}），"
            f"新结果 makespan={preview.get('makespan', '—')}。"
            f"请确认是否覆盖落库。"
        )
        pending_action = {
            "type": "confirm_persist",
            "confirm_token": token_data.get("confirm_token"),
            "expires_at": token_data.get("expires_at"),
            "preview": preview,
            "summary_zh": summary_zh,
        }
        return "pending", pending_action

    updated, save_err = save_schedule_results(
        str(plan_id),
        schedule_results,
        interpretation=interpretation,
        delivery_assessment=delivery_assessment,
        impact_summary=impact_summary,
        jobs=jobs,
        status=status,
    )
    if save_err:
        return "error", {"error": save_err}
    return "saved", {"plan_id": str(plan_id), "plan": updated}


def build_schedule_update_doc(
    schedule_results: Dict[str, Any],
    *,
    interpretation: Optional[Dict[str, Any]] = None,
    delivery_assessment: Optional[Dict[str, Any]] = None,
    impact_summary: Optional[Dict[str, Any]] = None,
    jobs: Optional[List[Any]] = None,
    status: str = "done",
) -> Dict[str, Any]:
    """由多算法 schedule_results 生成可写入 Mongo 的字段。"""
    best_sid, best_entry = _pick_best_schedule(schedule_results)
    schedule_result = dict(best_entry or {})
    if best_sid:
        schedule_result.setdefault("id", best_sid)
    schedule_result.setdefault("name", schedule_result.get("name") or best_sid or "best")

    doc: Dict[str, Any] = {
        "schedule_results": to_bson_safe(schedule_results),
        "schedule_result": to_bson_safe(schedule_result),
        "status": status,
        "scheduled_at": datetime.now(),
    }
    if interpretation is not None:
        doc["interpretation"] = to_bson_safe(interpretation)
    if delivery_assessment is not None:
        doc["delivery_assessment"] = to_bson_safe(delivery_assessment)
    if impact_summary is not None:
        doc["impact_summary"] = to_bson_safe(impact_summary)
    if jobs is not None:
        doc["jobs"] = to_bson_safe(list(jobs))
    return doc


def build_impact_summary_payload(
    impact_report: Optional[Dict[str, Any]],
    *,
    summary_zh: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """重排影响评估落库结构（含完整 impact_report 与时间戳）。"""
    if not impact_report or not isinstance(impact_report, dict):
        return None
    return {
        "summary_zh": summary_zh or impact_report.get("summary_zh") or "",
        "impact_report": to_bson_safe(impact_report),
        "event_type": impact_report.get("event_type"),
        "rescheduled_at": datetime.now(timezone.utc).isoformat(),
    }


def save_schedule_results(
    plan_id: str,
    schedule_results: Dict[str, Any],
    *,
    interpretation: Optional[Dict[str, Any]] = None,
    delivery_assessment: Optional[Dict[str, Any]] = None,
    impact_summary: Optional[Dict[str, Any]] = None,
    jobs: Optional[List[Any]] = None,
    status: str = "done",
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """将排程结果写入计划文档，返回更新后的 plan。"""
    if not plan_id:
        return None, "plan_id required"
    if not schedule_results:
        return None, "schedule_results required"
    if not plan_store.is_configured():
        return None, "plan_store not configured"

    update_doc = build_schedule_update_doc(
        schedule_results,
        interpretation=interpretation,
        delivery_assessment=delivery_assessment,
        impact_summary=impact_summary,
        jobs=jobs,
        status=status,
    )
    return plan_store.apply_plan_fields(plan_id, update_doc)
