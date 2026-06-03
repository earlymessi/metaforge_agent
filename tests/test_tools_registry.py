"""Tool 注册表测试。"""

import pytest

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, list_tools, register_tool, run_tool


def _echo_handler(params, ctx):
    return ToolResult(ok=True, data={"echo": params.get("x"), "ctx_keys": list(ctx.artifacts.keys())})


@pytest.fixture(autouse=True)
def _register_echo_tool():
    try:
        get_tool("test.echo")
    except KeyError:
        register_tool(
            ToolSpec(
                name="test.echo",
                description_zh="测试回显",
                input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
                output_schema={"type": "object"},
                handler=_echo_handler,
            )
        )


def test_list_tools_includes_registered():
    names = {t["name"] for t in list_tools()}
    assert "test.echo" in names


def test_run_tool_success():
    ctx = ToolContext(artifacts={"prev": 1})
    r = run_tool("test.echo", {"x": "hi"}, ctx)
    assert r.ok
    assert r.data["echo"] == "hi"


def test_run_tool_unknown_raises():
    with pytest.raises(KeyError, match="Unknown tool"):
        run_tool("nonexistent.tool", {}, ToolContext())


def test_get_tool():
    spec = get_tool("test.echo")
    assert spec.name == "test.echo"
