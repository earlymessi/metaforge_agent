from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_commitment_trace(
    *,
    status: str,
    stages: Optional[List[str]] = None,
    want_script: bool = False,
    tool_log: Optional[List[Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "stages": list(stages or []),
        "status": status,
        "want_script": bool(want_script),
        "tool_log": list(tool_log or []),
        "warnings": list(warnings or []),
    }
