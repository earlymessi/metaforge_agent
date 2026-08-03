"""Agent 内 ReAct 循环：LLM 逐步选 Tool，替代固定 build_rule_plan 分支。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from metaforge.orchestrator.llm import invoke
from metaforge.orchestrator.llm_config import llm_enabled, llm_fallback_rule


def llm_react_enabled_for(agent_id: str) -> bool:
    if not llm_enabled():
        return False
    if os.getenv("LLM_REACT_ENABLED", "0") != "1":
        return False
    allowed = os.getenv("LLM_REACT_AGENTS", "scheduling")
    ids = {x.strip() for x in allowed.split(",") if x.strip()}
    return agent_id in ids


def react_max_steps() -> int:
    try:
        return max(1, min(16, int(os.getenv("LLM_REACT_MAX_STEPS", "8"))))
    except ValueError:
        return 8


def decide_react_step(
    *,
    agent_id: str,
    name_zh: str,
    allowed_tools: List[str],
    message: str,
    params: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    artifacts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return invoke(
        "react_step",
        agent_id=agent_id,
        name_zh=name_zh,
        allowed_tools=allowed_tools,
        message=message,
        params=params,
        history=history or [],
        artifacts=artifacts or {},
    )
