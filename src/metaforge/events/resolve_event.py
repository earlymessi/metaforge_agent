"""统一事件信封解析：GLM 优先，失败回退规则。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from metaforge.events.llm_event import parse_event_with_llm
from metaforge.orchestrator.llm_config import llm_enabled, llm_fallback_rule
from metaforge.tools.events.parse_event import parse_event_message


def resolve_event_envelope(
    message: str,
    *,
    base_jobs: Optional[List[Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    params = params or {}
    text = (message or params.get("message") or "").strip()
    jobs = base_jobs if base_jobs is not None else params.get("base_jobs")

    if params.get("event_envelope"):
        env = dict(params["event_envelope"])
        env.setdefault("planner", "explicit")
        return env

    if not text:
        env = parse_event_message("", base_jobs=jobs)
        env["planner"] = "rule"
        return env

    use_llm = llm_enabled() and params.get("use_llm") is not False
    if use_llm:
        try:
            return parse_event_with_llm(text, base_jobs=jobs)
        except Exception as e:
            if not llm_fallback_rule():
                raise
            env = parse_event_message(text, base_jobs=jobs)
            env["planner"] = "rule_fallback"
            env["llm_error"] = str(e)[:300]
            return env

    env = parse_event_message(text, base_jobs=jobs)
    env["planner"] = "rule"
    return env
