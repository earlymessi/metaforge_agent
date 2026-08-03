from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_kitting_trace(
    *,
    status: str,
    stages: Optional[List[str]] = None,
    mode: Optional[str] = None,
    tool_log: Optional[List[Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build minimal kitting_trace payload for AgentResponse.artifacts."""
    return {
        "stages": list(stages or []),
        "status": status,
        "mode": mode,
        "tool_log": list(tool_log or []),
        "warnings": list(warnings or []),
    }
