"""GLM 事件解析（薄封装，逻辑在 orchestrator.llm）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from metaforge.orchestrator.llm import invoke
from metaforge.orchestrator.llm import parsers, prompts
from metaforge.orchestrator.llm.client import LlmClientError

build_event_system_prompt = prompts.event_system
build_event_user_prompt = lambda message, *, base_jobs=None: prompts.event_user(
    message, job_names=parsers.extract_job_names(base_jobs)
)
normalize_llm_event_payload = parsers.parse_event


def parse_event_with_llm(
    message: str,
    *,
    base_jobs: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    return invoke("event", message=message, base_jobs=base_jobs)


__all__ = [
    "LlmClientError",
    "build_event_system_prompt",
    "build_event_user_prompt",
    "normalize_llm_event_payload",
    "parse_event_with_llm",
]
