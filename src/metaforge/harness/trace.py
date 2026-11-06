"""Merge collab / strategy traces with harness RunEvents into one run_trace."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def merge_run_trace(
    *,
    run_events: Optional[List[Dict[str, Any]]] = None,
    collab_trace: Optional[Dict[str, Any]] = None,
    strategy_trace: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Unify planning observability without dropping legacy trace blocks."""
    events = list(run_events or [])
    collab = dict(collab_trace) if collab_trace else None
    strategy = strategy_trace
    if strategy is None and collab:
        strategy = collab.get("strategy_trace")

    return {
        "type": "run_trace",
        "kind": "run_trace",
        "run_id": run_id
        or (collab or {}).get("collab_run_id")
        or (strategy or {}).get("run_id"),
        "run_events": events,
        "collab_trace": collab,
        "strategy_trace": strategy,
        "event_count": len(events),
    }
