"""排程落库意图（原 pipeline Agent 合并入 scheduling）。"""

from __future__ import annotations

from typing import Any, Dict


def is_schedule_persist_message(message: str) -> bool:
    """用户要求排程结果写入计划库（HITL 或直写）。"""
    msg = (message or "").strip()
    if not msg:
        return False
    if any(k in msg for k in ("落库", "保存到数据库", "写入数据库", "保存到库")):
        return True
    if ("保存" in msg or "落库" in msg) and any(
        k in msg for k in ("排程", "计划", "生产计划")
    ):
        return True
    if "排程" in msg and "并" in msg and any(k in msg for k in ("保存", "落库", "写入")):
        return True
    return False


def wants_persist_request(message: str, params: Dict[str, Any] | None) -> bool:
    p = params or {}
    if p.get("confirm_token"):
        return True
    if p.get("persist_after") in (True, 1, "1", "true", "yes"):
        return True
    return is_schedule_persist_message(message)
