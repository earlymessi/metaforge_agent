"""data.confirm_persist — 校验 token（实际写库由 API 异步完成）。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.services.persist_store import get_pending
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    token = params.get("confirm_token") or ctx.extras.get("confirm_token")
    if not token:
        return ToolResult(ok=False, error="confirm_token required")

    confirm_fn = ctx.extras.get("confirm_persist_fn")
    if callable(confirm_fn):
        result = confirm_fn(token)
        if isinstance(result, dict) and result.get("error"):
            return ToolResult(ok=False, error=result["error"])
        if ctx.artifacts is not None:
            ctx.artifacts["persist_result"] = result
        return ToolResult(ok=True, data=result, artifacts_key="persist_result")

    entry = get_pending(token)
    if not entry:
        return ToolResult(ok=False, error="invalid_or_expired_token")

    data = {
        "status": "validated",
        "confirm_token": token,
        "plan_id": entry["plan_id"],
        "preview": entry.get("preview"),
        "message_zh": "Token 有效。请调用 POST /api/db/confirm_save 完成写库。",
    }
    if ctx.artifacts is not None:
        ctx.artifacts["persist_validation"] = data
    return ToolResult(ok=True, data=data, artifacts_key="persist_validation")


def register_data_confirm_persist_tool() -> None:
    name = "data.confirm_persist"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="校验 confirm_token 或经 extras 回调完成落库",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
