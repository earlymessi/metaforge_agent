"""Optional LLM reasoning summary; failures return None (skip)."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

_MAX_SUMMARY_CHARS = 200


def summarize_agent_result(
    artifacts: Dict[str, Any],
    *,
    llm_client: Any = None,
    agent_id: str = "",
) -> Optional[str]:
    """Return a short Chinese summary, or None if client missing / call fails."""
    if llm_client is None:
        return None

    complete = getattr(llm_client, "complete", None)
    if complete is None:
        return None

    try:
        payload = json.dumps(artifacts, ensure_ascii=False, default=str)
        prompt = (
            f"用一两句中文概括以下{agent_id or '分析'}结果，不要列表：\n{payload[:1500]}"
        )
        text = complete(prompt)
        if text is None:
            return None
        summary = str(text).strip()
        if not summary:
            return None
        if len(summary) > _MAX_SUMMARY_CHARS:
            summary = summary[:_MAX_SUMMARY_CHARS].rstrip() + "…"
        return summary
    except Exception:
        return None
