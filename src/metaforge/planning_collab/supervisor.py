"""Planning Supervisor: Order/Constraint/Resource → S1 strategy pipeline."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from metaforge.planning_collab.agents.constraint import run_constraint_agent
from metaforge.planning_collab.agents.order import run_order_agent
from metaforge.planning_collab.agents.resource import run_resource_agent
from metaforge.planning_collab.protocol import AgentResult, AgentTask, PlanningTaskState
from metaforge.planning_collab.summarize import summarize_agent_result
from metaforge.planning_collab.trace import build_collab_trace
from metaforge.strategy.pipeline import run_planning
from metaforge.strategy.run_state import get_run

_COLLAB_STORE: Dict[str, Dict[str, Any]] = {}
# Internal: AgentResult objects for collab_trace assembly (not API-facing).
_AGENT_RESULTS_STORE: Dict[str, Dict[str, AgentResult]] = {}


def _fail_closed() -> bool:
    return os.getenv("COLLAB_FAIL_CLOSED", "0") == "1"


def _run_one(
    agent_id: str,
    runner,
    task: AgentTask,
    llm_client: Any,
) -> AgentResult:
    try:
        result = runner(task)
    except Exception as exc:  # noqa: BLE001 - degrade per-agent
        return AgentResult(
            agent_id=agent_id,
            status="failed",
            summary=f"{agent_id} failed: {exc}",
            artifacts={},
            warnings=[str(exc)],
            reasoning_summary=None,
        )
    if result.status == "success" and result.artifacts:
        summary = summarize_agent_result(
            result.artifacts,
            llm_client=llm_client,
            agent_id=agent_id,
        )
        result.reasoning_summary = summary
    return result


def run_collab_analyze(
    *,
    user_goal: str,
    jobs: Any,
    machines: Any = None,
    llm_client: Any = None,
    parallel: bool = True,
) -> Dict[str, Any]:
    """Run three analysis agents; return artifacts (+ task state snapshot)."""
    jobs_list = list(jobs or [])
    machines_list = list(machines or [])
    state = PlanningTaskState.new(
        user_goal=user_goal,
        jobs=jobs_list,
        machines=machines_list,
    )
    state.current_stage = "analyze"
    state.status = "RUNNING"

    base_inputs = {
        "user_goal": user_goal,
        "jobs": jobs_list,
        "machines": machines_list,
    }

    order_task = AgentTask(
        task_id=f"{state.task_id}-order",
        agent_id="order",
        objective="分析订单关键/临期/优先级",
        inputs=dict(base_inputs),
    )
    # Constraint may use order_analysis; run order first for richer inputs,
    # then constraint+resource (resource independent). For simplicity and
    # plan "可并行", we still allow parallel with empty order_analysis on
    # constraint — Supervisor merges after. Prefer sequential: order → others.

    order_result = _run_one("order", run_order_agent, order_task, llm_client)

    constraint_inputs = dict(base_inputs)
    if order_result.status == "success":
        constraint_inputs["order_analysis"] = order_result.artifacts

    constraint_task = AgentTask(
        task_id=f"{state.task_id}-constraint",
        agent_id="constraint",
        objective="提出硬/软约束候选",
        inputs=constraint_inputs,
    )
    resource_task = AgentTask(
        task_id=f"{state.task_id}-resource",
        agent_id="resource",
        objective="估算资源负载与瓶颈",
        inputs=dict(base_inputs),
    )

    results: Dict[str, AgentResult] = {"order": order_result}

    if parallel:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(
                    _run_one, "constraint", run_constraint_agent, constraint_task, llm_client
                ): "constraint",
                pool.submit(
                    _run_one, "resource", run_resource_agent, resource_task, llm_client
                ): "resource",
            }
            for fut in as_completed(futures):
                aid = futures[fut]
                results[aid] = fut.result()
    else:
        results["constraint"] = _run_one(
            "constraint", run_constraint_agent, constraint_task, llm_client
        )
        results["resource"] = _run_one(
            "resource", run_resource_agent, resource_task, llm_client
        )

    artifacts: Dict[str, Any] = {}
    warnings: List[str] = list(state.warnings)
    completed: List[str] = []
    failed: List[str] = []

    key_map = {
        "order": "order_analysis",
        "constraint": "constraint_analysis",
        "resource": "resource_analysis",
    }
    for agent_id, art_key in key_map.items():
        result = results[agent_id]
        warnings.extend(result.warnings or [])
        if result.status == "success":
            payload = dict(result.artifacts)
            if result.reasoning_summary:
                payload["reasoning_summary"] = result.reasoning_summary
            if result.summary:
                payload["summary"] = result.summary
            artifacts[art_key] = payload
            completed.append(agent_id)
        else:
            failed.append(agent_id)
            warnings.append(f"{agent_id} analysis failed: {result.summary}")

    if failed and _fail_closed():
        state.status = "FAILED"
        state.warnings = warnings
        state.completed_agents = completed
        state.pending_agents = [a for a in state.pending_agents if a not in completed]
        state.artifacts = artifacts
        snap = state.to_dict()
        collab_trace = build_collab_trace(
            collab_run_id=state.run_id,
            stage="analyze",
            status="FAILED",
            agent_results=results,
            failed_agents=failed,
            warnings=warnings,
        )
        snap["collab_trace"] = collab_trace
        _COLLAB_STORE[state.run_id] = snap
        _AGENT_RESULTS_STORE[state.run_id] = results
        return {
            "status": "FAILED",
            "run_id": state.run_id,
            "task_id": state.task_id,
            "artifacts": artifacts,
            "warnings": warnings,
            "task_state": snap,
            "failed_agents": failed,
            "collab_trace": collab_trace,
        }

    state.artifacts = artifacts
    state.completed_agents = completed
    state.pending_agents = []
    state.warnings = warnings
    state.status = "ANALYZED"
    state.current_stage = "strategy"
    snap = state.to_dict()
    collab_trace = build_collab_trace(
        collab_run_id=state.run_id,
        stage="analyze",
        status="ANALYZED",
        agent_results=results,
        failed_agents=failed,
        warnings=warnings,
    )
    snap["collab_trace"] = collab_trace
    _COLLAB_STORE[state.run_id] = snap
    _AGENT_RESULTS_STORE[state.run_id] = results
    return {
        "status": "ANALYZED",
        "run_id": state.run_id,
        "task_id": state.task_id,
        "artifacts": artifacts,
        "warnings": warnings,
        "task_state": snap,
        "failed_agents": failed,
        "collab_trace": collab_trace,
    }


def run_collab(
    *,
    user_goal: str,
    jobs: Any,
    machines: Any = None,
    skip_strategy_hitl: bool = False,
    llm_client: Any = None,
    problem: Any = None,
    parallel: bool = True,
) -> Dict[str, Any]:
    """Analyze → S1 generate_strategy/run_planning; return package + artifacts."""
    analysis = run_collab_analyze(
        user_goal=user_goal,
        jobs=jobs,
        machines=machines,
        llm_client=llm_client,
        parallel=parallel,
    )
    if analysis.get("status") == "FAILED":
        return analysis

    arts = analysis.get("artifacts") or {}
    agent_results = _AGENT_RESULTS_STORE.pop(str(analysis.get("run_id") or ""), {})
    planning = run_planning(
        user_goal=user_goal,
        jobs=jobs,
        machines=machines,
        skip_strategy_hitl=skip_strategy_hitl,
        llm_client=llm_client,
        problem=problem,
        order_analysis=arts.get("order_analysis"),
        constraint_analysis=arts.get("constraint_analysis"),
        resource_analysis=arts.get("resource_analysis"),
    )

    out = dict(planning)
    out["artifacts"] = arts
    out["collab_run_id"] = analysis.get("run_id")
    out["collab_warnings"] = analysis.get("warnings") or []
    out.setdefault("warnings", [])
    out["warnings"] = list(out["warnings"]) + list(out["collab_warnings"])

    collab_trace = build_collab_trace(
        collab_run_id=str(analysis.get("run_id") or ""),
        stage=str(out.get("stage") or "done"),
        status=str(out.get("status") or ""),
        agent_results=agent_results,
        failed_agents=analysis.get("failed_agents") or [],
        warnings=out["warnings"],
        planning_run=out,
    )
    out["collab_trace"] = collab_trace

    # Keep collab store in sync with planning outcome.
    snap = dict(analysis.get("task_state") or {})
    snap["artifacts"] = {
        **arts,
        "strategy": out.get("strategy_approved")
        or out.get("strategy_draft")
        or (out.get("package") or {}).get("strategy"),
        "solver_policy": out.get("solver_policy"),
        "candidate_schedules": out.get("candidate_schedules"),
        "evaluation": out.get("evaluation") or (out.get("package") or {}).get("evaluation"),
    }
    snap["status"] = out.get("status")
    snap["current_stage"] = out.get("stage") or snap.get("current_stage")
    snap["planning_run_id"] = out.get("run_id")
    snap["collab_trace"] = collab_trace
    _COLLAB_STORE[analysis["run_id"]] = snap
    out["task_state"] = snap
    return out


def get_collab_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Lookup collab TaskState snapshot (also tries S1 planning run_id)."""
    if run_id in _COLLAB_STORE:
        return _COLLAB_STORE[run_id]
    # Allow querying via planning run_id stored on snap.
    for snap in _COLLAB_STORE.values():
        if snap.get("planning_run_id") == run_id:
            return snap
    planning = get_run(run_id)
    if planning is not None:
        return planning
    return None
