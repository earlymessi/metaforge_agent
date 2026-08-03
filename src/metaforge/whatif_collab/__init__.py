"""What-if collab: fixed-stage variant comparison orchestration."""

from metaforge.whatif_collab.pipeline import run_whatif
from metaforge.whatif_collab.plan_steps import (
    build_variants_from_params,
    build_whatif_plan_steps,
)
from metaforge.whatif_collab.trace import build_whatif_trace

__all__ = [
    "run_whatif",
    "build_variants_from_params",
    "build_whatif_plan_steps",
    "build_whatif_trace",
]
