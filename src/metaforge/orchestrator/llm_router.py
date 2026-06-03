"""GLM 意图路由（薄封装，逻辑在 orchestrator.llm）。"""



from __future__ import annotations



from typing import Any, Dict



from metaforge.orchestrator.llm import invoke

from metaforge.orchestrator.llm import parsers, prompts



build_router_system_prompt = prompts.router_system

build_router_user_prompt = prompts.router_user

normalize_router_payload = parsers.parse_router





def classify_message_with_llm(message: str) -> Dict[str, Any]:

    """GLM 意图路由；精确规则护栏在 resolve_agent_route._apply_route_guards。"""

    return invoke("router", message=message)


