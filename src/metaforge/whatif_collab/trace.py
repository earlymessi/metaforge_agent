from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_whatif_trace(
    *,
    status: str,
    stages: Optional[List[str]] = None,
    recommend_metric: Optional[str] = None,
    tool_log: Optional[List[Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "stages": list(stages or []),
        "status": status,
        "recommend_metric": recommend_metric,
        "tool_log": list(tool_log or []),
        "warnings": list(warnings or []),
    }
