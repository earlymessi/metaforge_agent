from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from metaforge.strategy.catalog import list_constraint_catalog
from metaforge.strategy.presets import list_presets

_MAX_GOAL_LEN = 500
_MAX_ORDERS = 30
_ORDER_FIELDS = ("job_id", "id", "name", "due_date", "due", "priority", "customer")


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _order_key(job: Any) -> tuple:
    if not isinstance(job, dict):
        return (1, 0, str(job))
    due = job.get("due_date", job.get("due"))
    try:
        due_val = float(due) if due is not None else float("inf")
    except (TypeError, ValueError):
        due_val = float("inf")
    priority = job.get("priority", 0)
    try:
        priority_val = -float(priority)
    except (TypeError, ValueError):
        priority_val = 0.0
    return (0, due_val, priority_val)


def _summarize_order(job: Any) -> Dict[str, Any]:
    if isinstance(job, str):
        return {"job_id": job}
    if not isinstance(job, dict):
        return {"job_id": str(job)}

    summary: Dict[str, Any] = {}
    for key in _ORDER_FIELDS:
        if key in job and job[key] is not None and job[key] != "":
            out_key = "due" if key == "due_date" else key
            if out_key == "job_id" and key in ("id", "name"):
                summary.setdefault("job_id", job[key])
            elif out_key not in summary:
                summary[out_key] = job[key]
    if "job_id" not in summary:
        for fallback in ("id", "name"):
            if fallback in job:
                summary["job_id"] = job[fallback]
                break
    return summary


def _summarize_orders(jobs: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    items = list(jobs or [])
    ranked = sorted(items, key=_order_key)
    return [_summarize_order(job) for job in ranked[:_MAX_ORDERS]]


def _summarize_machines(machines: Optional[Iterable[Any]]) -> List[str]:
    out: List[str] = []
    for machine in machines or []:
        if isinstance(machine, str):
            out.append(machine)
        elif isinstance(machine, dict):
            mid = machine.get("machine_id") or machine.get("id") or machine.get("name")
            if mid is not None:
                out.append(str(mid))
        else:
            out.append(str(machine))
    return out


def _bom_item_count(bom: Any) -> int:
    if bom is None:
        return 0
    if isinstance(bom, dict):
        items = bom.get("items")
        if isinstance(items, list):
            return len(items)
        return len(bom)
    if isinstance(bom, list):
        return len(bom)
    return 0


def _gantt_op_count(gantt_data: Any) -> int:
    if gantt_data is None:
        return 0
    if isinstance(gantt_data, list):
        return len(gantt_data)
    return 0


def build_for_strategy_generation(
    *,
    user_goal: str,
    jobs: Optional[Iterable[Any]] = None,
    machines: Optional[Iterable[Any]] = None,
    gantt_data: Any = None,
    bom: Any = None,
    existing_constraints: Optional[List[Any]] = None,
    downtime: Optional[List[Any]] = None,
    order_analysis: Optional[Dict[str, Any]] = None,
    constraint_analysis: Optional[Dict[str, Any]] = None,
    resource_analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a fixed-budget context dict for strategy generation prompts."""
    catalog = list_constraint_catalog()
    constraint_catalog_short = [
        {"type": entry["type"], "kind": entry["kind"]} for entry in catalog
    ]

    return {
        "user_goal": _truncate(user_goal, _MAX_GOAL_LEN),
        "orders_summary": _summarize_orders(jobs),
        "machines_summary": _summarize_machines(machines),
        "constraint_catalog_short": constraint_catalog_short,
        "preset_ids": [p["id"] for p in list_presets()],
        "bom_item_count": _bom_item_count(bom),
        "gantt_op_count": _gantt_op_count(gantt_data),
        "existing_constraints": list(existing_constraints or [])[:20],
        "downtime_summary": list(downtime or [])[:20],
        "order_analysis": dict(order_analysis or {}),
        "constraint_analysis": dict(constraint_analysis or {}),
        "resource_analysis": dict(resource_analysis or {}),
    }
