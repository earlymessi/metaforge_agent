"""Agent 内 LLM Plan（薄封装 + 规则回退）。"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from metaforge.agents.base import PlanStep
from metaforge.orchestrator.llm import invoke
from metaforge.orchestrator.llm import parsers, prompts
from metaforge.orchestrator.llm_config import llm_enabled, llm_fallback_rule

build_plan_system_prompt = prompts.plan_system
build_plan_user_prompt = prompts.plan_user
normalize_plan_steps = parsers.parse_plan_steps


def llm_plan_enabled_for(agent_id: str) -> bool:
    if not llm_enabled():
        return False
    if os.getenv("LLM_PLAN_ENABLED", "1") != "1":
        return False
    allowed = os.getenv("LLM_PLAN_AGENTS", "scheduling")
    ids = {x.strip() for x in allowed.split(",") if x.strip()}
    return agent_id in ids


def build_plan_with_llm(
    *,
    agent_id: str,
    name_zh: str,
    allowed_tools: List[str],
    message: str,
    params: Optional[Dict[str, Any]] = None,
) -> List[PlanStep]:
    return invoke(
        "plan",
        agent_id=agent_id,
        name_zh=name_zh,
        allowed_tools=allowed_tools,
        message=message,
        params=params,
    )


def resolve_agent_plan_steps(
    *,
    agent_id: str,
    name_zh: str,
    allowed_tools: List[str],
    message: str,
    params: Optional[Dict[str, Any]],
    rule_builder: Callable[[], List[PlanStep]],
) -> tuple[List[PlanStep], str]:
    rule_steps = rule_builder()
    if len(rule_steps) == 1 and rule_steps[0].tool in (
        "scheduling.ask_clarification",
    ):
        return rule_steps, "rule"
    if not llm_plan_enabled_for(agent_id):
        return rule_steps, "rule"

    try:
        steps = build_plan_with_llm(
            agent_id=agent_id,
            name_zh=name_zh,
            allowed_tools=allowed_tools,
            message=message,
            params=params,
        )
        return steps, "llm"
    except Exception:
        if not llm_fallback_rule():
            raise
        return rule_steps, "rule_fallback"
