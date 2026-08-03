"""Preview/plan steps mirroring events_collab fixed stages (no Tool execution)."""

from __future__ import annotations

import re
from typing import List

from metaforge.agents.base import AgentRequest, PlanStep

_CATALOG_QUERY_RE = re.compile(
    r"支持哪些|有哪些事件|事件类型|能处理什么异常",
    re.I,
)


def build_events_plan_steps(request: AgentRequest) -> List[PlanStep]:
    """Fixed Tool chain for orchestrator preview / trace (aligned with run_events)."""
    from metaforge.orchestrator.router import has_pending_insert_job_intake

    message = request.message or ""
    params = dict(request.params or {})
    context = dict(request.context or {})
    envelope = params.get("event_envelope")
    if not (isinstance(envelope, dict) and envelope.get("event_type")):
        envelope = None

    if has_pending_insert_job_intake(context):
        return [
            PlanStep("m1", "events.merge_insert_job", {"message": message}),
            PlanStep("m2", "events.check_insert_job", {"message": message}),
            PlanStep("s2", "events.reschedule", {}),
            PlanStep("s3", "delivery.explain_impact", {}),
        ]

    msg = message.strip()
    if msg and _CATALOG_QUERY_RE.search(msg):
        return [PlanStep("s0", "events.list_event_types", {})]

    steps: List[PlanStep] = [
        PlanStep("s0", "execution.get_state", {}, optional=True),
    ]
    if not params.get("skip_parse"):
        steps.append(
            PlanStep(
                "s1",
                "events.parse_event",
                {"message": message, "event_envelope": envelope},
            )
        )
    steps.append(PlanStep("s1b", "events.check_insert_job", {"message": message}))
    reschedule_params = {}
    if envelope:
        reschedule_params["event_envelope"] = envelope
    steps.append(PlanStep("s2", "events.reschedule", reschedule_params))
    steps.append(PlanStep("s3", "delivery.compare_commitment", {}, optional=True))
    steps.append(PlanStep("s4", "delivery.explain_impact", {}))
    return steps
