"""Planning Collab Skill — wraps Supervisor run_collab under Harness."""

from __future__ import annotations

from typing import Any, Dict

from metaforge.harness.skill import SkillSpec, register_skill
from metaforge.planning_collab.supervisor import run_collab, run_collab_analyze

_REGISTERED = False


def _entry_run(**kwargs: Any) -> Dict[str, Any]:
    return run_collab(**kwargs)


def _entry_analyze(**kwargs: Any) -> Dict[str, Any]:
    return run_collab_analyze(**kwargs)


def ensure_registered() -> None:
    """Idempotent register — safe after test registry clears."""
    global _REGISTERED
    register_skill(
        SkillSpec(
            id="planning_collab",
            name_zh="智能排产协作",
            description_zh="Order/Constraint/Resource → SchedulingStrategy → Solver → Package",
            allowed_tools=[
                "planning.strategy_generate",
                "planning.strategy_evaluate",
                "planning.run",
            ],
            risk_level="ask",
            entrypoint=_entry_run,
        )
    )
    register_skill(
        SkillSpec(
            id="planning_collab.analyze",
            name_zh="智能排产·仅分析",
            description_zh="只跑三分析 Agent，不求解",
            allowed_tools=[],
            risk_level="allow",
            entrypoint=_entry_analyze,
        )
    )
    _REGISTERED = True


ensure_registered()
