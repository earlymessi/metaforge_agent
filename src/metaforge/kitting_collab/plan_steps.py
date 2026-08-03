"""Preview/plan steps mirroring kitting_collab fixed stages (no Tool execution)."""

from __future__ import annotations

import re
from typing import List

from metaforge.agents.base import AgentRequest, PlanStep

_SCHEDULE_THEN_PREDICT_RE = re.compile(r"先排程|先排产|预测物料|物料仿真", re.I)


def resolve_kitting_mode(message: str = "", params: dict | None = None) -> str:
    params = dict(params or {})
    if params.get("mode"):
        return str(params["mode"])
    if _SCHEDULE_THEN_PREDICT_RE.search((message or "").strip()):
        return "schedule_then_predict"
    return "check_only"


def build_kitting_plan_steps(request: AgentRequest) -> List[PlanStep]:
    """Fixed Tool chain for orchestrator preview / trace (aligned with run_kitting)."""
    mode = resolve_kitting_mode(request.message or "", request.params)
    request.params["mode"] = mode
    solvers_default = request.params.get("solvers")

    if mode == "check_only":
        return [
            PlanStep("s1", "material.check_static", {}),
            PlanStep("s2", "material.compute_delays", {}, optional=True),
            PlanStep("s3", "kitting.build_report", {}),
        ]
    if mode == "schedule_then_predict":
        return [
            PlanStep(
                "s1",
                "scheduling.run",
                {"solvers": solvers_default or ["spt"]},
            ),
            PlanStep("s2", "material.predict", {}),
            PlanStep("s3", "kitting.build_report", {}),
        ]
    # kit_then_schedule (and any other mode)
    return [
        PlanStep("s1", "material.check_static", {}),
        PlanStep("s2", "material.compute_delays", {}, optional=True),
        PlanStep(
            "s3",
            "scheduling.run",
            {"solvers": solvers_default or ["spt", "ts"]},
        ),
        PlanStep("s4", "material.predict", {}, optional=True),
        PlanStep("s5", "kitting.build_report", {}),
    ]
