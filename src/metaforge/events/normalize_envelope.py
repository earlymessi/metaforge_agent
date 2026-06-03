"""事件信封归一化：LLM 与规则解析共用同一套 params 默认值与类型校验。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

VALID_EVENT_TYPES = frozenset(
    (
        "machine_breakdown",
        "insert_order",
        "planned_downtime",
        "material_delay",
        "priority_change",
        "order_cancel",
        "quantity_change",
        "due_date_change",
    )
)


def coerce_hours(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    if s in ("now", "立即", "当前", "马上", "立刻"):
        return 0.0
    m = re.match(r"^(\d+(?:\.\d+)?)\s*h(?:ours?)?$", s)
    if m:
        return float(m.group(1))
    try:
        return float(s)
    except ValueError:
        return default


def extract_job_names(base_jobs: Optional[List[Any]]) -> List[str]:
    names: List[str] = []
    for j in base_jobs or []:
        n = j.get("name") if isinstance(j, dict) else getattr(j, "name", None)
        if n:
            names.append(str(n))
    return names


def normalize_event_type(event_type: str, *, default: str = "machine_breakdown") -> str:
    et = str(event_type or default).strip()
    if et not in VALID_EVENT_TYPES:
        return default
    return et


def normalize_event_params(
    event_type: str,
    params: Optional[Dict[str, Any]],
    *,
    base_jobs: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """按 event_type 补齐/校验 params（LLM 与规则路径共用）。"""
    p = dict(params or {})
    names = extract_job_names(base_jobs)
    default_job = names[0] if names else "工单A"
    default_job_b = names[-1] if names else "工单B"

    if event_type == "machine_breakdown":
        p.setdefault("machine_id", 0)
        p.setdefault("breakdown_start", 0.0)
        p.setdefault("breakdown_duration", 4.0)
        try:
            p["machine_id"] = max(0, int(p["machine_id"]))
        except (TypeError, ValueError):
            p["machine_id"] = 0
        p["breakdown_start"] = coerce_hours(p.get("breakdown_start"), 0.0)
        p["breakdown_duration"] = coerce_hours(p.get("breakdown_duration"), 4.0)
    elif event_type == "insert_order":
        p.setdefault("mode", "local_repair")
    elif event_type == "planned_downtime":
        blocks = p.get("downtime_blocks")
        if not isinstance(blocks, list) or not blocks:
            mid = int(p.get("machine_id", 0))
            dur = coerce_hours(
                p.get("duration_hours", p.get("breakdown_duration", 8.0)), 8.0
            )
            p["downtime_blocks"] = [
                {"machine_id": mid, "start": 0.0, "end": dur, "label": "planned_downtime"}
            ]
        else:
            for blk in blocks:
                if isinstance(blk, dict):
                    if "start" in blk:
                        blk["start"] = coerce_hours(blk["start"], 0.0)
                    if "end" in blk:
                        blk["end"] = coerce_hours(blk["end"], 0.0)
    elif event_type == "material_delay":
        p.setdefault("job_name", default_job)
        p.setdefault("delay_hours", 24.0)
        p["delay_hours"] = coerce_hours(p.get("delay_hours"), 24.0)
    elif event_type == "priority_change":
        if not p.get("changes"):
            p["changes"] = [{"job_name": default_job, "new_priority": 100}]
    elif event_type == "order_cancel":
        if not p.get("job_names"):
            p["job_names"] = [default_job_b]
    elif event_type == "quantity_change":
        if not p.get("changes"):
            p["changes"] = [{"job_name": default_job, "new_quantity": 2}]
    elif event_type == "due_date_change":
        p.setdefault("due_date_changes", [])

    return p


def build_event_envelope(
    event_type: str,
    params: Optional[Dict[str, Any]],
    *,
    base_jobs: Optional[List[Any]] = None,
    reschedule_options: Optional[Dict[str, Any]] = None,
    summary_zh: str = "",
    planner: str = "rule",
) -> Dict[str, Any]:
    et = normalize_event_type(event_type)
    jobs = list(base_jobs or [])
    normalized = normalize_event_params(et, params, base_jobs=jobs)
    opts = dict(reschedule_options or {})
    return {
        "event_type": et,
        "base_jobs": jobs,
        "params": normalized,
        "reschedule_options": opts,
        "summary_zh": str(summary_zh or "")[:200],
        "planner": planner,
    }
