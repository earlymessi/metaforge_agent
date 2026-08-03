from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from metaforge.services.event_reschedule import dispatch_event_reschedule

DispatchFn = Callable[[dict[str, Any]], dict[str, Any]]
AsyncDispatchFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _build_step_envelope(base_envelope: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    step_envelope = {
        **base_envelope,
        "event_type": step["event_type"],
        "params": dict(step.get("params") or {}),
    }
    if step.get("t") is not None:
        pe = dict(step_envelope.get("production_execution") or {})
        pe.setdefault("sim_time", float(step["t"]))
        step_envelope["production_execution"] = pe
    return step_envelope


def _record_success(
    base_envelope: dict[str, Any],
    result: dict[str, Any],
) -> Any:
    impact = result.get("impact_report") or result
    if result.get("production_execution"):
        base_envelope["production_execution"] = result["production_execution"]
    if result.get("updated_jobs"):
        base_envelope["base_jobs"] = result["updated_jobs"]
    return impact


def run_scenario(
    scenario: dict[str, Any],
    *,
    envelope: Optional[dict[str, Any]] = None,
    dispatch: Optional[DispatchFn] = None,
) -> dict[str, Any]:
    """
    Run scenario steps sequentially via dispatch_event_reschedule.

    On step failure (exception or result.error): stop remaining steps.
    Returns { status, timeline, impact }.
    """
    steps = scenario.get("steps") or []
    if not isinstance(steps, list):
        raise ValueError("scenario steps must be a list")

    base_envelope = dict(envelope or {})
    dispatch_fn = dispatch or dispatch_event_reschedule
    timeline: list[dict[str, Any]] = []
    last_impact: Any = None
    status = "completed"

    for idx, step in enumerate(steps):
        if not isinstance(step, dict) or not step.get("event_type"):
            timeline.append(
                {
                    "index": idx,
                    "event_type": None,
                    "status": "failed",
                    "error": "invalid step: event_type required",
                }
            )
            status = "failed"
            break

        step_envelope = _build_step_envelope(base_envelope, step)
        try:
            result = dispatch_fn(step_envelope)
        except Exception as exc:  # noqa: BLE001 — fail-stop timeline
            timeline.append(
                {
                    "index": idx,
                    "event_type": step["event_type"],
                    "status": "failed",
                    "error": str(exc),
                }
            )
            status = "failed"
            break

        if isinstance(result, dict) and result.get("error"):
            timeline.append(
                {
                    "index": idx,
                    "event_type": step["event_type"],
                    "status": "failed",
                    "error": result.get("error"),
                    "result": result,
                }
            )
            status = "failed"
            break

        if isinstance(result, dict):
            last_impact = _record_success(base_envelope, result)

        timeline.append(
            {
                "index": idx,
                "event_type": step["event_type"],
                "status": "ok",
                "result_keys": list(result.keys()) if isinstance(result, dict) else [],
            }
        )

    return {
        "status": status,
        "timeline": timeline,
        "impact": last_impact,
        "scenario_id": scenario.get("id"),
        "scenario_name": scenario.get("name"),
    }


async def run_scenario_async(
    scenario: dict[str, Any],
    *,
    envelope: Optional[dict[str, Any]] = None,
    dispatch: AsyncDispatchFn,
) -> dict[str, Any]:
    """Async variant used by FastAPI (dispatch may sync MES execution)."""
    steps = scenario.get("steps") or []
    if not isinstance(steps, list):
        raise ValueError("scenario steps must be a list")

    base_envelope = dict(envelope or {})
    timeline: list[dict[str, Any]] = []
    last_impact: Any = None
    status = "completed"

    for idx, step in enumerate(steps):
        if not isinstance(step, dict) or not step.get("event_type"):
            timeline.append(
                {
                    "index": idx,
                    "event_type": None,
                    "status": "failed",
                    "error": "invalid step: event_type required",
                }
            )
            status = "failed"
            break

        step_envelope = _build_step_envelope(base_envelope, step)
        try:
            result = await dispatch(step_envelope)
        except Exception as exc:  # noqa: BLE001
            timeline.append(
                {
                    "index": idx,
                    "event_type": step["event_type"],
                    "status": "failed",
                    "error": str(exc),
                }
            )
            status = "failed"
            break

        if isinstance(result, dict) and result.get("error"):
            timeline.append(
                {
                    "index": idx,
                    "event_type": step["event_type"],
                    "status": "failed",
                    "error": result.get("error"),
                    "result": result,
                }
            )
            status = "failed"
            break

        if isinstance(result, dict):
            last_impact = _record_success(base_envelope, result)

        timeline.append(
            {
                "index": idx,
                "event_type": step["event_type"],
                "status": "ok",
            }
        )

    return {
        "status": status,
        "timeline": timeline,
        "impact": last_impact,
        "scenario_id": scenario.get("id"),
        "scenario_name": scenario.get("name"),
    }
