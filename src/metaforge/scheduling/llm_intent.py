"""GLM 排程意图（薄封装，逻辑在 orchestrator.llm）。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from metaforge.orchestrator.llm import invoke
from metaforge.orchestrator.llm import parsers, prompts
from metaforge.orchestrator.llm.client import LlmClientError
from metaforge.scheduling.context import ContextManager

build_system_prompt = prompts.scheduling_system
build_scheduling_user_prompt = prompts.scheduling_user
normalize_llm_payload = parsers.parse_scheduling


def parse_message_with_llm(
    message: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    benchmark_file: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    params = dict(params or {})
    session_context = ContextManager.to_llm_context(session_id)
    data = invoke(
        "scheduling",
        message=message,
        params=params,
        benchmark_file=benchmark_file,
        session_context=session_context,
    )
    if benchmark_file and not data.get("benchmark_file"):
        data["benchmark_file"] = benchmark_file
    return data


__all__ = [
    "LlmClientError",
    "build_system_prompt",
    "build_scheduling_user_prompt",
    "normalize_llm_payload",
    "parse_message_with_llm",
]
