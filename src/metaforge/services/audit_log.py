"""编排与 Agent 操作审计（最小实现，可扩展写 Mongo）。"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_audit_logger = logging.getLogger("metaforge.audit")


def audit_enabled() -> bool:
    return os.getenv("AUDIT_LOG_ENABLED", "1").strip().lower() not in ("0", "false", "off")


def log_agent_action(
    *,
    action: str,
    agent_id: str,
    message: str = "",
    status: str = "",
    session_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """记录编排/Agent 关键动作（默认写应用日志；`AUDIT_LOG_MONGO=1` 时可扩展）。"""
    if not audit_enabled():
        return
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "agent_id": agent_id,
        "status": status,
        "message_preview": (message or "")[:200],
        "session_id": session_id,
        "plan_id": plan_id,
    }
    if extra:
        payload["extra"] = {k: v for k, v in extra.items() if k not in ("custom_data", "jobs")}
    _audit_logger.info("audit %s", payload)
    if os.getenv("AUDIT_LOG_MONGO", "0").strip().lower() in ("1", "true", "yes"):
        _append_mongo_audit(payload)


def _append_mongo_audit(payload: Dict[str, Any]) -> None:
    try:
        from metaforge.utils.mongodb import get_database

        db = get_database()
        if db is not None:
            db["audit_log"].insert_one(payload)
    except Exception as exc:
        _audit_logger.warning("audit mongo skip: %s", exc)
