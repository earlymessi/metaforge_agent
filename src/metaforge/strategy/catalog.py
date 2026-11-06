from __future__ import annotations

from typing import Any, Dict, List, Optional

HARD_CONSTRAINT_TYPES = {
    "order_on_time",
    "machine_unavailable",
    "frozen_operations",
    "precedence",
    "skill_required",
    "tooling_exclusive",
}

SOFT_CONSTRAINT_TYPES = {
    "reduce_changeover",
    "avoid_machine_overload",
    "load_balance",
    "schedule_stability",
    "prefer_overtime",
    "avoid_overtime",
    "prefer_outsourcing",
    "avoid_outsourcing",
    "energy_shift_preference",
}

SOFT_FOLDS_INTO: Dict[str, Optional[str]] = {
    "reduce_changeover": "setup_changeover",
    "load_balance": "machine_busy_cv",
    "schedule_stability": "schedule_stability",
    "energy_shift_preference": "energy_cost",
}


def list_constraint_catalog(domain: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return a short catalog table suitable for frontend display.

    Default (domain=None / non-fab): classic JSSP types only — unchanged.
    domain == "fab": classic + FAB types (FAB entries carry domain="fab").
    """
    hard = [
        {"type": t, "kind": "hard", "folds_into_objective": None}
        for t in sorted(HARD_CONSTRAINT_TYPES)
    ]
    soft = [
        {
            "type": t,
            "kind": "soft",
            "folds_into_objective": SOFT_FOLDS_INTO.get(t),
        }
        for t in sorted(SOFT_CONSTRAINT_TYPES)
    ]
    catalog = hard + soft
    if domain == "fab":
        from metaforge.fab.catalog import list_fab_constraint_catalog

        catalog = catalog + list_fab_constraint_catalog()
    return catalog
