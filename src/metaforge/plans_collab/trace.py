from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_plans_trace(
    *,
    status: str,
    stages: Optional[List[str]] = None,
    action: Optional[str] = None,
    intent_planner: Optional[str] = None,
    tool_log: Optional[List[Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "stages": list(stages or []),
        "status": status,
        "action": action,
        "intent_planner": intent_planner,
        "tool_log": list(tool_log or []),
        "warnings": list(warnings or []),
    }
