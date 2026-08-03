from __future__ import annotations

from typing import Any, Dict, List, Optional

from metaforge.strategy.capability_matrix import get_capability
from metaforge.strategy.models import SchedulingStrategy, SolverPolicy
from metaforge.utils.solver_registry import get_solver_spec, resolve_solver_id

_DEFAULT_PRIMARY = ["ts", "ga"]
_DEFAULT_FALLBACK = "edd"
_DEFAULT_MAX_CANDIDATES = 3
_DEFAULT_TIME_BUDGET = 8.0

_TEMPLATE_PRIMARY: Dict[str, List[str]] = {
    "delivery": ["ts", "ga"],
    "makespan": ["ts", "sa"],
    "cost": ["sa", "ga"],
    "balance_load": ["ga", "aco"],
    "throughput": ["ts", "ga"],
    "balanced": ["ts", "ga"],
}

_TEMPLATE_FALLBACK: Dict[str, str] = {
    "delivery": "edd",
    "makespan": "spt",
    "cost": "spt",
    "balance_load": "mwkr",
    "throughput": "spt",
    "balanced": "edd",
}


def _normalize_solver_ids(names: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for name in names:
        sid = resolve_solver_id(name)
        if sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def _eligible_primary(solver_id: str) -> bool:
    cap = get_capability(solver_id)
    if cap["family"] == "rl" and not cap["supports_dynamic_weights"]:
        return False
    return True


def _filter_primary(primary: List[str]) -> List[str]:
    return [sid for sid in primary if _eligible_primary(sid)]


def _solver_parameters(primary: List[str]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for sid in primary:
        spec = get_solver_spec(sid)
        params[sid] = dict(spec.default_params)
    return params


def _time_budget_for(n_jobs: int, override: Optional[float]) -> float:
    if override is not None:
        return float(override)
    return min(30.0, _DEFAULT_TIME_BUDGET + max(0, n_jobs - 10) * 0.3)


def build_solver_policy(
    strategy: SchedulingStrategy,
    *,
    n_jobs: int = 0,
) -> SolverPolicy:
    prefs = strategy.solver_preferences or {}
    template = strategy.base_template or "balanced"

    primary = _normalize_solver_ids(
        list(prefs.get("primary_solvers") or _TEMPLATE_PRIMARY.get(template, _DEFAULT_PRIMARY))
    )
    primary = _filter_primary(primary)
    if not primary:
        primary = list(_DEFAULT_PRIMARY)

    fallback_raw = prefs.get("fallback_solver") or _TEMPLATE_FALLBACK.get(template, _DEFAULT_FALLBACK)
    fallback: Optional[str] = resolve_solver_id(str(fallback_raw))

    max_candidates = int(prefs.get("max_candidates") or _DEFAULT_MAX_CANDIDATES)
    max_candidates = max(1, min(max_candidates, _DEFAULT_MAX_CANDIDATES))

    time_budget = _time_budget_for(n_jobs, prefs.get("time_budget_seconds"))

    reason_parts = [f"template={template}", f"primary={','.join(primary)}"]
    if fallback:
        reason_parts.append(f"fallback={fallback}")
    reason = "; ".join(reason_parts)

    return SolverPolicy(
        primary_solvers=primary[:max_candidates],
        fallback_solver=fallback,
        time_budget_seconds=time_budget,
        max_candidates=max_candidates,
        parameters=_solver_parameters(primary[:max_candidates]),
        reason=reason,
    )
