from __future__ import annotations

from typing import Any, Dict

from metaforge.utils.solver_registry import get_solver_spec, resolve_solver_id


def get_capability(solver_id: str) -> Dict[str, Any]:
    """Return strategy-layer capability view for a solver."""
    spec = get_solver_spec(resolve_solver_id(solver_id))
    supports_weights = spec.supports_weights_in_search
    if spec.family == "rl":
        supports_weights = False
    return {
        "supports_dynamic_weights": supports_weights,
        "family": spec.family,
        "supports_multiobjective_search": spec.supports_weights_in_search,
        "supports_complex_hard_constraints": False,
    }
