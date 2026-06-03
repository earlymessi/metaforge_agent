"""pytest 全局：测试默认使用内存 Session/HITL，关闭 MCP。"""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _test_store_defaults():
    os.environ["SESSION_STORE"] = "memory"
    os.environ["MCP_ENABLED"] = "0"
    os.environ["LLM_SUMMARIZE_ENABLED"] = "0"
    yield
