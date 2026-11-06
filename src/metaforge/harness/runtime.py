"""Thin AgentRuntime: run AgentTask → AgentResult and record RunEvents."""

from __future__ import annotations

import threading
from typing import Callable, List, Optional

from metaforge.harness.types import RunEvent
from metaforge.planning_collab.protocol import AgentResult, AgentTask

AgentRunner = Callable[[AgentTask], AgentResult]


class AgentRuntime:
    """Process-local runtime for collaborative agents (no framework lock-in)."""

    def __init__(self) -> None:
        self._events: List[RunEvent] = []
        self._lock = threading.Lock()

    @property
    def events(self) -> List[RunEvent]:
        with self._lock:
            return list(self._events)

    def drain_events(self) -> List[RunEvent]:
        with self._lock:
            out = list(self._events)
            self._events.clear()
            return out

    def emit(
        self,
        event_type: str,
        *,
        agent_id: Optional[str] = None,
        **payload,
    ) -> RunEvent:
        ev = RunEvent(type=event_type, agent_id=agent_id, payload=dict(payload))
        with self._lock:
            self._events.append(ev)
        return ev

    def run_agent(self, task: AgentTask, runner: AgentRunner) -> AgentResult:
        self.emit(
            "agent.start",
            agent_id=task.agent_id,
            task_id=task.task_id,
            objective=task.objective,
        )
        try:
            result = runner(task)
        except Exception as exc:  # noqa: BLE001 - harness boundary
            self.emit(
                "agent.error",
                agent_id=task.agent_id,
                task_id=task.task_id,
                error=str(exc),
            )
            result = AgentResult(
                agent_id=task.agent_id,
                status="failed",
                summary=f"{task.agent_id} failed: {exc}",
                artifacts={},
                warnings=[str(exc)],
                reasoning_summary=None,
            )
            self.emit(
                "agent.end",
                agent_id=task.agent_id,
                task_id=task.task_id,
                status=result.status,
            )
            return result

        status = result.status if result is not None else "failed"
        self.emit(
            "agent.end",
            agent_id=task.agent_id,
            task_id=task.task_id,
            status=status,
        )
        return result