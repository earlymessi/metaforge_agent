"""工单列表变更（扩展事件用）。"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


def _job_name(job: Any) -> str:
    if isinstance(job, dict):
        return str(job.get("name", ""))
    return str(getattr(job, "name", ""))


def apply_priority_changes(jobs: List[Any], changes: List[Dict[str, Any]]) -> List[Any]:
    out = copy.deepcopy(jobs)
    cmap = {c["job_name"]: int(c["new_priority"]) for c in changes}
    for job in out:
        n = _job_name(job)
        if n in cmap:
            if isinstance(job, dict):
                job["priority"] = cmap[n]
            else:
                job.priority = cmap[n]
    return out


def apply_order_cancel(jobs: List[Any], job_names: List[str]) -> List[Any]:
    names = set(job_names)
    return [j for j in jobs if _job_name(j) not in names]


def apply_material_delay(jobs: List[Any], job_name: str, delay_hours: float) -> List[Any]:
    out = copy.deepcopy(jobs)
    for job in out:
        if _job_name(job) == job_name:
            base = 0.0
            if isinstance(job, dict):
                base = float(job.get("material_arrival") or 0.0)
                job["material_arrival"] = base + float(delay_hours)
            else:
                base = float(getattr(job, "material_arrival", 0) or 0.0)
                job.material_arrival = base + float(delay_hours)
    return out


def apply_quantity_changes(jobs: List[Any], changes: List[Dict[str, Any]]) -> List[Any]:
    out = copy.deepcopy(jobs)
    cmap = {c["job_name"]: int(c["new_quantity"]) for c in changes}
    for job in out:
        n = _job_name(job)
        if n in cmap:
            if isinstance(job, dict):
                job["quantity"] = cmap[n]
            else:
                job.quantity = cmap[n]
    return out


def merge_downtime_blocks(
    resource_config: Optional[Dict[str, Any]],
    new_blocks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    cfg = dict(resource_config or {})
    existing = list(cfg.get("downtime_blocks") or [])
    existing.extend(new_blocks)
    cfg["downtime_blocks"] = existing
    cfg.setdefault("_id", "global_config")
    return cfg
