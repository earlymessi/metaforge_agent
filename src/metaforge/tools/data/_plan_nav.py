"""计划 Tool 完成后跳转排程中心（增/改/查；删除与纯列表除外）。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from metaforge.plans.intent import should_navigate_aps

APS_UI_ACTION = {"type": "navigate", "path": "/aps"}


def enrich_active_from_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    jobs = doc.get("jobs") or []
    return {
        "plan_id": doc.get("id"),
        "plan_name": doc.get("plan_name"),
        "jobs": jobs,
        "job_count": len(jobs),
        "plan_status": doc.get("status"),
        "has_schedule": bool(doc.get("schedule_results") or doc.get("schedule_result")),
    }


def apply_active_plan(
    ctx,
    active: Dict[str, Any],
    *,
    action: Optional[str] = None,
    navigate: Optional[bool] = None,
    reason: str = "计划操作",
) -> None:
    if ctx.artifacts is None:
        return
    ctx.artifacts["active_plan"] = active
    ctx.artifacts["loaded_plan"] = active
    if active.get("plan_id"):
        ctx.plan_id = active["plan_id"]
        ctx.custom_data = active.get("jobs") or None
    do_nav = navigate if navigate is not None else should_navigate_aps(action or "")
    if do_nav:
        ctx.artifacts["ui_action"] = {**APS_UI_ACTION, "reason": reason}
