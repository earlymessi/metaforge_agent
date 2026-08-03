"""Collab-level execution trace (Supervisor + AgentResult + S1 strategy_trace)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from metaforge.planning_collab.protocol import AgentResult


def _agent_result_brief(result: AgentResult) -> Dict[str, Any]:
    return {
        "agent_id": result.agent_id,
        "status": result.status,
        "summary": result.summary,
        "reasoning_summary": result.reasoning_summary,
        "warnings": list(result.warnings or []),
        "artifact_keys": sorted((result.artifacts or {}).keys()),
    }


def build_collab_trace(
    *,
    collab_run_id: str,
    stage: str,
    status: str,
    agent_results: Optional[Dict[str, AgentResult]] = None,
    failed_agents: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    planning_run: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a mergeable collab trace block."""
    agents: List[Dict[str, Any]] = []
    if agent_results:
        for aid in ("order", "constraint", "resource"):
            if aid in agent_results:
                agents.append(_agent_result_brief(agent_results[aid]))
        for aid, result in agent_results.items():
            if aid not in ("order", "constraint", "resource"):
                agents.append(_agent_result_brief(result))

    strategy_trace = None
    if planning_run:
        strategy_trace = planning_run.get("strategy_trace") or planning_run.get(
            "execution_trace"
        )
        if strategy_trace is None:
            from metaforge.strategy.trace import build_strategy_trace

            strategy_trace = build_strategy_trace(planning_run)

    return {
        "type": "collab_trace",
        "kind": "collab_trace",
        "collab_run_id": collab_run_id,
        "stage": stage,
        "status": status,
        "supervisor": {
            "stages": ["analyze", "strategy", "solve"]
            if status == "COMPLETED"
            else ["analyze"]
            if stage == "analyze"
            else ["analyze", stage],
            "failed_agents": list(failed_agents or []),
        },
        "agents": agents,
        "warnings": list(warnings or []),
        "strategy_trace": strategy_trace,
    }
