"""Bridge: Orchestrator events intent → events_collab fixed pipeline."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from metaforge.agents.base import AgentRequest, AgentResponse, BaseAgent, PlanStep
from metaforge.events_collab.pipeline import run_events
from metaforge.events_collab.plan_steps import build_events_plan_steps


class EventsCollabBridge(BaseAgent):
    """Thin agent: fixed-stage events_collab pipeline (replaces EventsAgentRunner)."""

    agent_id = "events"
    name_zh = "异常重排"
    allowed_tools: List[str] = []

    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:
        self._plan_planner = "events_collab"
        return build_events_plan_steps(request)

    def build_plan(self, request: AgentRequest) -> List[PlanStep]:
        """Skip LLM plan — events collab is pure fixed orchestration."""
        return self.build_rule_plan(request)

    def run(
        self,
        request: AgentRequest,
        *,
        on_step_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_step_done: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentResponse:
        if on_step_start:
            on_step_start({"step_id": "collab", "tool": "events.collab.run"})

        out = run_events(
            message=request.message or "",
            context=request.context,
            params=request.params,
        )

        if on_step_done:
            on_step_done(
                {
                    "step_id": "collab",
                    "tool": "events.collab.run",
                    "status": out.get("status"),
                }
            )

        status = out.get("status") or "failed"
        artifacts = dict(out.get("artifacts") or {})
        return AgentResponse(
            status=status,
            agent_id=self.agent_id,
            summary_zh=out.get("summary_zh") or "",
            plan=list(out.get("plan") or []),
            artifacts=artifacts,
            pending_action=out.get("pending_action"),
            error=out.get("error"),
            plan_planner="events_collab",
            ui_action=out.get("ui_action"),
        )
