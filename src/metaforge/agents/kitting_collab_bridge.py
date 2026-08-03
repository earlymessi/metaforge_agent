"""Bridge: Orchestrator kitting intent → kitting_collab fixed pipeline."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from metaforge.agents.base import AgentRequest, AgentResponse, BaseAgent, PlanStep
from metaforge.kitting_collab.pipeline import run_kitting
from metaforge.kitting_collab.plan_steps import build_kitting_plan_steps


class KittingCollabBridge(BaseAgent):
    """Thin agent: fixed-stage kitting_collab pipeline (replaces KittingAgentRunner)."""

    agent_id = "kitting"
    name_zh = "齐套顾问"
    allowed_tools: List[str] = []

    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:
        self._plan_planner = "kitting_collab"
        return build_kitting_plan_steps(request)

    def build_plan(self, request: AgentRequest) -> List[PlanStep]:
        """Skip LLM plan — kitting collab is pure fixed orchestration."""
        return self.build_rule_plan(request)

    def run(
        self,
        request: AgentRequest,
        *,
        on_step_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_step_done: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentResponse:
        if on_step_start:
            on_step_start({"step_id": "collab", "tool": "kitting.collab.run"})

        out = run_kitting(
            message=request.message or "",
            context=request.context,
            params=request.params,
        )

        if on_step_done:
            on_step_done(
                {
                    "step_id": "collab",
                    "tool": "kitting.collab.run",
                    "status": out.get("status"),
                }
            )

        return AgentResponse(
            status=out.get("status") or "failed",
            agent_id=self.agent_id,
            summary_zh=out.get("summary_zh") or "",
            plan=list(out.get("plan") or []),
            artifacts=dict(out.get("artifacts") or {}),
            pending_action=out.get("pending_action"),
            error=out.get("error"),
            plan_planner="kitting_collab",
            ui_action=out.get("ui_action"),
        )
