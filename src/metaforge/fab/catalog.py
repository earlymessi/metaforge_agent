"""FAB-only constraint types. Must NOT be merged into strategy.catalog defaults."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

FAB_HARD_CONSTRAINT_TYPES = {
    "photo_machine_dedication",
    "max_lag_between_ops",
    "batch_same_family",
    "batch_capacity",
    "batch_synchronized",
}

FAB_SOFT_CONSTRAINT_TYPES = {
    "prefer_batch_fill",
    "dedication_load_balance",
}

FAB_SOFT_FOLDS_INTO: Dict[str, Optional[str]] = {
    "prefer_batch_fill": None,
    "dedication_load_balance": "machine_busy_cv",
}

FAB_AREAS = {
    "diffusion_furnace",
    "photolithography",
    "etch_timelink",
}


def list_fab_constraint_catalog() -> List[Dict[str, Any]]:
    hard = [
        {"type": t, "kind": "hard", "folds_into_objective": None, "domain": "fab"}
        for t in sorted(FAB_HARD_CONSTRAINT_TYPES)
    ]
    soft = [
        {
            "type": t,
            "kind": "soft",
            "folds_into_objective": FAB_SOFT_FOLDS_INTO.get(t),
            "domain": "fab",
        }
        for t in sorted(FAB_SOFT_CONSTRAINT_TYPES)
    ]
    return hard + soft
