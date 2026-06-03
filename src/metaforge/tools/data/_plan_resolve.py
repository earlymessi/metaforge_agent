"""解析 plan_id / 名称查询为单条计划。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from metaforge.services import plan_store


def resolve_plan_ref(
    *,
    plan_id: Optional[str] = None,
    query: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if plan_id:
        doc, err = plan_store.get_plan(str(plan_id))
        if err or not doc:
            return None, err or "plan not found"
        return doc, None

    q = (query or "").strip()
    if not q:
        return None, "plan_id or query required"

    found, err = plan_store.find_by_query(q)
    if err:
        return None, err
    if not found:
        return None, f"plan not found: {q}"
    if isinstance(found, dict) and found.get("ambiguous"):
        names = [p.get("plan_name") for p in found.get("matches", [])[:5]]
        return None, f"ambiguous plan: {', '.join(names)}"
    return found, None
