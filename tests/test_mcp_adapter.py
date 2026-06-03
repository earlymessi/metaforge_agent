"""MCP 适配器测试。"""

import os
from unittest.mock import patch

from metaforge.orchestrator.mcp_adapter import invoke_mcp_tool, list_mcp_tools, mcp_enabled


def test_mcp_disabled_by_default():
    assert mcp_enabled() is False
    assert list_mcp_tools() == []
    r = invoke_mcp_tool("notify.dingtalk", {})
    assert not r.ok


@patch.dict(os.environ, {"MCP_ENABLED": "1"})
def test_mcp_enabled_without_server():
    assert mcp_enabled() is True
    tools = list_mcp_tools()
    assert len(tools) >= 1
    r = invoke_mcp_tool("notify.dingtalk", {})
    assert not r.ok
    assert "MCP_SERVER_URL" in (r.error or "")
