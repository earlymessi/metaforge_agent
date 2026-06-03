"""Tool 失败 / 低置信度时的 LLM 反思层。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from metaforge.orchestrator.llm import invoke
from metaforge.orchestrator.llm_config import llm_enabled


def llm_reflect_enabled() -> bool:
    if not llm_enabled():
        return False
    return os.getenv("LLM_REFLECT_ENABLED", "0") == "1"


def reflect_max_retries() -> int:
    try:
        return max(0, min(3, int(os.getenv("LLM_REFLECT_MAX_RETRIES", "2"))))
    except ValueError:
        return 2


def reflect_tool_failure(
    *,
    agent_id: str,
    name_zh: str,
    allowed_tools: List[str],
    message: str,
    failed_tool: str,
    error: str,
    params: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    artifacts: Optional[Dict[str, Any]] = None,
    retry_count: int = 0,
) -> Dict[str, Any]:
    return invoke(
        "reflect",
        agent_id=agent_id,
        name_zh=name_zh,
        allowed_tools=allowed_tools,
        message=message,
        params=params,
        history=history or [],
        artifacts=artifacts or {},
        failed_tool=failed_tool,
        error=error,
        retry_count=retry_count,
    )
