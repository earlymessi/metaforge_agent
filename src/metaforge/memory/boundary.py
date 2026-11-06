"""State / Memory / business-fact boundary helpers."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Literal, Optional, Set

Kind = Literal["factual", "task", "session", "unknown"]

# Keys that must remain business-fact authority (Mongo/Service), not Memory.
FACTUAL_KEYS: Set[str] = {
    "gantt_data",
    "gantt",
    "jobs",
    "machines",
    "bom",
    "inventory",
    "materials",
    "stock",
    "production_plan",
    "schedule_results",
    "candidate_schedules",
    "custom_data",
}

SESSION_HINTS: Set[str] = {
    "pending_clarification",
    "user_preference",
    "preferences",
    "insert_job_intake",
    "last_intent",
}

TASK_HINTS: Set[str] = {
    "order_analysis",
    "constraint_analysis",
    "resource_analysis",
    "strategy_draft",
    "strategy_approved",
    "collab_trace",
    "run_events",
    "context_hash",
}


def memory_strict() -> bool:
    return os.getenv("METAFORGE_MEMORY_STRICT", "0") == "1"


def classify_key(key: str) -> Kind:
    k = (key or "").strip()
    if not k:
        return "unknown"
    # namespace:key from working_key
    leaf = k.split(":")[-1] if ":" in k else k
    low = leaf.lower()
    if low in FACTUAL_KEYS or any(low.endswith(f"_{fk}") for fk in ("gantt", "jobs")):
        return "factual"
    if low in TASK_HINTS or "artifact" in low:
        return "task"
    if low in SESSION_HINTS or low.startswith("pref_"):
        return "session"
    return "unknown"


def classify_payload(payload: Any) -> Kind:
    if not isinstance(payload, dict):
        return "unknown"
    kinds = {classify_key(str(k)) for k in payload.keys()}
    if "factual" in kinds:
        return "factual"
    if "task" in kinds:
        return "task"
    if "session" in kinds:
        return "session"
    return "unknown"


def check_memory_write(
    scope: str,
    key: str,
    value: Any = None,
) -> List[str]:
    """Return warning messages if write violates boundary. Empty = ok."""
    warnings: List[str] = []
    kind = classify_key(key)
    if kind == "factual":
        warnings.append(
            f"refusing factual authority in memory scope={scope} key={key}; "
            "use Mongo/Service as source of truth"
        )
    if isinstance(value, dict):
        for nested_key in value.keys():
            if classify_key(str(nested_key)) == "factual":
                warnings.append(
                    f"memory value embeds factual key '{nested_key}' under {scope}:{key}"
                )
    if scope == "episodic" and kind == "task":
        warnings.append(
            f"task artifacts should live in PlanningTaskState, not episodic ({key})"
        )
    return warnings


def assert_memory_write(scope: str, key: str, value: Any = None) -> List[str]:
    """Check write; raise RuntimeError when METAFORGE_MEMORY_STRICT=1 and violations."""
    warnings = check_memory_write(scope, key, value)
    if warnings and memory_strict():
        raise RuntimeError("; ".join(warnings))
    return warnings
