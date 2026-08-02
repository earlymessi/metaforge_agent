from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, List, Optional, Set, Tuple

from metaforge.strategy.catalog import HARD_CONSTRAINT_TYPES, SOFT_CONSTRAINT_TYPES
from metaforge.strategy.models import Constraint, SchedulingStrategy


def _collect_ids(items: Optional[Iterable[Any]], keys: Tuple[str, ...]) -> Set[str]:
    ids: Set[str] = set()
    for item in items or []:
        if isinstance(item, str):
            ids.add(item)
        elif isinstance(item, dict):
            for key in keys:
                value = item.get(key)
                if value is not None and value != "":
                    ids.add(str(value))
                    break
    return ids


def _job_ids(jobs: Optional[Iterable[Any]]) -> Set[str]:
    return _collect_ids(jobs, ("job_id", "id", "name"))


def _machine_ids(machines: Optional[Iterable[Any]]) -> Set[str]:
    return _collect_ids(machines, ("machine_id", "id", "name"))


def _needs_simulated_resource(
    constraint_type: str,
    *,
    workers: Optional[Iterable[Any]],
    tools: Optional[Iterable[Any]],
) -> bool:
    if constraint_type == "skill_required":
        return not workers
    if constraint_type == "tooling_exclusive":
        return not tools
    return False


def _validate_hard_constraint(
    constraint: Constraint,
    *,
    job_ids: Set[str],
    machine_ids: Set[str],
    workers: Optional[Iterable[Any]],
    tools: Optional[Iterable[Any]],
    allow_simulated: bool,
    errors: List[str],
    simulated_fields: List[str],
) -> None:
    ctype = constraint.type
    params = constraint.params

    if ctype == "order_on_time":
        job_id = params.get("job_id")
        if job_id is None or str(job_id) not in job_ids:
            errors.append(f"order_on_time: job_id {job_id!r} not found in jobs")
        return

    if ctype == "machine_unavailable":
        machine_id = params.get("machine_id")
        if machine_id is None or str(machine_id) not in machine_ids:
            errors.append(f"machine_unavailable: machine_id {machine_id!r} not found in machines")
        return

    if ctype in ("skill_required", "tooling_exclusive"):
        job_id = params.get("job_id")
        if job_id is not None and str(job_id) not in job_ids:
            errors.append(f"{ctype}: job_id {job_id!r} not found in jobs")
            return

        if _needs_simulated_resource(ctype, workers=workers, tools=tools):
            if allow_simulated:
                if ctype not in simulated_fields:
                    simulated_fields.append(ctype)
            else:
                resource = "workers" if ctype == "skill_required" else "tools"
                errors.append(f"{ctype}: {resource} data required but not provided")


def validate_strategy(
    strategy: SchedulingStrategy,
    *,
    jobs: Iterable[Any],
    machines: Iterable[Any],
    workers: Optional[Iterable[Any]] = None,
    tools: Optional[Iterable[Any]] = None,
    allow_simulated: bool = True,
) -> Tuple[bool, List[str], SchedulingStrategy]:
    errors: List[str] = []
    fixed = deepcopy(strategy)
    simulated_fields = list(fixed.provenance.get("simulated_fields") or [])

    job_ids = _job_ids(jobs)
    machine_ids = _machine_ids(machines)

    for constraint in strategy.hard_constraints:
        if constraint.type not in HARD_CONSTRAINT_TYPES:
            errors.append(f"Unknown hard constraint type: {constraint.type}")
            continue
        _validate_hard_constraint(
            constraint,
            job_ids=job_ids,
            machine_ids=machine_ids,
            workers=workers,
            tools=tools,
            allow_simulated=allow_simulated,
            errors=errors,
            simulated_fields=simulated_fields,
        )

    for constraint in strategy.soft_constraints:
        if constraint.type not in SOFT_CONSTRAINT_TYPES:
            errors.append(f"Unknown soft constraint type: {constraint.type}")

    fixed.provenance = dict(fixed.provenance)
    fixed.provenance["simulated_fields"] = simulated_fields

    return len(errors) == 0, errors, fixed
