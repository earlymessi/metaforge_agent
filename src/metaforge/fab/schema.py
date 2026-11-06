"""Validate FAB scenario packs (hand-written; no external JSON-Schema dep)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from metaforge.fab.catalog import (
    FAB_AREAS,
    FAB_HARD_CONSTRAINT_TYPES,
    FAB_SOFT_CONSTRAINT_TYPES,
)


def validate_scenario_dict(data: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(data, dict):
        return False, ["scenario root must be an object"]

    if str(data.get("schema_version") or "") != "1":
        errors.append("schema_version must be '1'")

    scenario_id = data.get("scenario_id")
    if not scenario_id or not isinstance(scenario_id, str):
        errors.append("scenario_id is required")

    if data.get("domain") != "fab":
        errors.append("domain must be 'fab'")

    area = data.get("area")
    if area not in FAB_AREAS:
        errors.append(f"area must be one of {sorted(FAB_AREAS)}; got {area!r}")

    if not data.get("title"):
        errors.append("title is required")

    entities = data.get("entities")
    if not isinstance(entities, dict):
        errors.append("entities must be an object")
    else:
        machines = entities.get("machines")
        lots = entities.get("lots")
        if not isinstance(machines, list) or not machines:
            errors.append("entities.machines must be a non-empty list")
        if not isinstance(lots, list) or not lots:
            errors.append("entities.lots must be a non-empty list")

    for i, c in enumerate(data.get("constraints_hard") or []):
        if not isinstance(c, dict) or not c.get("type"):
            errors.append(f"constraints_hard[{i}] must have type")
            continue
        if c["type"] not in FAB_HARD_CONSTRAINT_TYPES:
            errors.append(f"constraints_hard[{i}]: unknown FAB hard type {c['type']!r}")

    for i, c in enumerate(data.get("constraints_soft") or []):
        if not isinstance(c, dict) or not c.get("type"):
            errors.append(f"constraints_soft[{i}] must have type")
            continue
        if c["type"] not in FAB_SOFT_CONSTRAINT_TYPES:
            errors.append(f"constraints_soft[{i}]: unknown FAB soft type {c['type']!r}")

    objs = data.get("objectives_default")
    if objs is not None and not isinstance(objs, (dict, list)):
        errors.append("objectives_default must be object or list")

    return len(errors) == 0, errors


def require_valid(data: Dict[str, Any]) -> None:
    ok, errors = validate_scenario_dict(data)
    if not ok:
        raise ValueError("invalid FAB scenario: " + "; ".join(errors))
