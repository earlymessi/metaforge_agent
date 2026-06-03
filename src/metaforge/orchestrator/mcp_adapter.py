"""MCP 外部工具适配器（Phase 6 骨架，默认关闭）。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from metaforge.tools.base import ToolResult

# 白名单：仅允许非核心、可失败的外部能力
_MCP_TOOL_CATALOG: List[Dict[str, Any]] = [
    {
        "name": "notify.dingtalk",
        "description_zh": "排程完成后发送钉钉通知（需配置 MCP 服务端）",
        "enabled": False,
    },
    {
        "name": "erp.fetch_orders",
        "description_zh": "从 ERP 拉取订单并转为 custom_data（需配置 MCP 服务端）",
        "enabled": False,
    },
]


def mcp_enabled() -> bool:
    return os.getenv("MCP_ENABLED", "0") == "1"


def list_mcp_tools() -> List[Dict[str, Any]]:
    if not mcp_enabled():
        return []
    return [dict(t) for t in _MCP_TOOL_CATALOG]


def invoke_mcp_tool(name: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
    if not mcp_enabled():
        return ToolResult(ok=False, error="MCP_ENABLED is not set")
    allowed = {t["name"] for t in _MCP_TOOL_CATALOG}
    if name not in allowed:
        return ToolResult(ok=False, error=f"mcp tool not allowed: {name}")
    server = (os.getenv("MCP_SERVER_URL") or "").strip()
    if not server:
        return ToolResult(
            ok=False,
            error="MCP_SERVER_URL not configured; adapter is a stub in Phase 6",
        )
    return ToolResult(
        ok=False,
        error=f"MCP invoke not implemented for {name}; configure MCP_SERVER_URL and Phase 6+ client",
    )
