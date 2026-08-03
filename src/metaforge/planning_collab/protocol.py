from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class AgentTask:
    task_id: str
    agent_id: str  # order | constraint | resource
    objective: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "objective": self.objective,
            "inputs": dict(self.inputs),
            "dependencies": list(self.dependencies),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTask":
        return cls(
            task_id=str(data["task_id"]),
            agent_id=str(data["agent_id"]),
            objective=str(data.get("objective") or ""),
            inputs=dict(data.get("inputs") or {}),
            dependencies=list(data.get("dependencies") or []),
        )


@dataclass
class AgentResult:
    agent_id: str
    status: str  # success | failed | skipped
    summary: str
    artifacts: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    reasoning_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "summary": self.summary,
            "artifacts": dict(self.artifacts),
            "warnings": list(self.warnings),
            "reasoning_summary": self.reasoning_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentResult":
        return cls(
            agent_id=str(data["agent_id"]),
            status=str(data.get("status") or "failed"),
            summary=str(data.get("summary") or ""),
            artifacts=dict(data.get("artifacts") or {}),
            warnings=list(data.get("warnings") or []),
            reasoning_summary=data.get("reasoning_summary"),
        )


@dataclass
class PlanningTaskState:
    task_id: str
    run_id: str
    user_goal: str
    production_input: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    completed_agents: List[str] = field(default_factory=list)
    pending_agents: List[str] = field(default_factory=list)
    current_stage: str = "analyze"  # analyze | strategy | hitl | solve | evaluate | done
    status: str = "pending"
    warnings: List[str] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        user_goal: str,
        jobs: Optional[List[Dict[str, Any]]] = None,
        *,
        machines: Optional[List[Any]] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **extra_input: Any,
    ) -> "PlanningTaskState":
        production_input: Dict[str, Any] = {"jobs": list(jobs or [])}
        if machines is not None:
            production_input["machines"] = list(machines)
        production_input.update(extra_input)
        tid = task_id or str(uuid4())
        rid = run_id or tid
        return cls(
            task_id=tid,
            run_id=rid,
            user_goal=user_goal,
            production_input=production_input,
            artifacts={},
            completed_agents=[],
            pending_agents=["order", "constraint", "resource"],
            current_stage="analyze",
            status="pending",
            warnings=[],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "user_goal": self.user_goal,
            "production_input": dict(self.production_input),
            "artifacts": dict(self.artifacts),
            "completed_agents": list(self.completed_agents),
            "pending_agents": list(self.pending_agents),
            "current_stage": self.current_stage,
            "status": self.status,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanningTaskState":
        return cls(
            task_id=str(data["task_id"]),
            run_id=str(data.get("run_id") or data["task_id"]),
            user_goal=str(data.get("user_goal") or ""),
            production_input=dict(data.get("production_input") or {}),
            artifacts=dict(data.get("artifacts") or {}),
            completed_agents=list(data.get("completed_agents") or []),
            pending_agents=list(data.get("pending_agents") or []),
            current_stage=str(data.get("current_stage") or "analyze"),
            status=str(data.get("status") or "pending"),
            warnings=list(data.get("warnings") or []),
        )
