"""Tool 执行完成后，由 LLM 组织面向用户的最终答复。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from metaforge.orchestrator.llm import invoke
from metaforge.orchestrator.llm_config import llm_enabled, llm_fallback_rule


def llm_summarize_enabled() -> bool:
    if not llm_enabled():
        return False
    return os.getenv("LLM_SUMMARIZE_ENABLED", "1") != "0"


def summarize_agent_response(
    *,
    agent_id: str,
    name_zh: str,
    message: str,
    plan_log: Optional[List[Dict[str, Any]]] = None,
    artifacts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return invoke(
        "summarize",
        agent_id=agent_id,
        name_zh=name_zh,
        message=message,
        plan_log=plan_log or [],
        artifacts=artifacts or {},
    )
