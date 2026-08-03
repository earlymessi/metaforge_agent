from __future__ import annotations

from typing import Any


def _resolve_recommended_id(package: dict) -> str | None:
    evaluation = package.get("evaluation") or {}
    return package.get("recommended_schedule_id") or evaluation.get("recommended_schedule_id")


def _resolve_candidates(package: dict) -> list:
    evaluation = package.get("evaluation") or {}
    return (
        evaluation.get("candidates")
        or package.get("candidates")
        or package.get("candidate_schedules")
        or []
    )


def _match_candidate(candidates: list, recommended_id: str) -> dict | None:
    for candidate in candidates:
        for key in ("schedule_id", "solver", "id"):
            if candidate.get(key) == recommended_id:
                return candidate
    return None


def _solver_id_from_candidate(candidate: dict, recommended_id: str) -> str:
    return (
        candidate.get("solver")
        or candidate.get("schedule_id")
        or candidate.get("id")
        or recommended_id
    )


def extract_recommended_gantt(
    *, package: dict | None = None, candidates: list | None = None
) -> tuple[str, list]:
    """Extract solver id and gantt_data for the recommended schedule from a planning package."""
    package = package or {}

    recommended_id = _resolve_recommended_id(package)
    if not recommended_id:
        raise ValueError("no recommended schedule id in package")

    resolved_candidates = candidates if candidates is not None else _resolve_candidates(package)
    candidate = _match_candidate(resolved_candidates, recommended_id)
    if candidate is None:
        raise ValueError(f"recommended schedule {recommended_id!r} not found in candidates")

    gantt_data = candidate.get("gantt_data")
    if not gantt_data:
        raise ValueError(f"recommended schedule {recommended_id!r} has no gantt_data")

    return _solver_id_from_candidate(candidate, recommended_id), list(gantt_data)
