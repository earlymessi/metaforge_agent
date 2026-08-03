from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_RUN_STORE: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run(**fields: Any) -> Dict[str, Any]:
    """Create an in-memory planning run and return the stored reference."""
    run_id = str(uuid.uuid4())
    now = _now_iso()
    run: Dict[str, Any] = {
        "run_id": run_id,
        "status": "WAITING_APPROVAL",
        "stage": "hitl_strategy",
        "strategy_draft": None,
        "strategy_approved": None,
        "candidate_schedules": [],
        "evaluation": None,
        "package": None,
        "error": None,
        "warnings": [],
        "created_at": now,
        "updated_at": now,
    }
    run.update(fields)
    _RUN_STORE[run_id] = run
    return run


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    return _RUN_STORE.get(run_id)


def update_run(run_id: str, **fields: Any) -> Dict[str, Any]:
    run = _RUN_STORE.get(run_id)
    if run is None:
        raise KeyError(f"run not found: {run_id!r}")
    run.update(fields)
    run["updated_at"] = _now_iso()
    return run
