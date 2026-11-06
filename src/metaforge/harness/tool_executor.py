"""Unified ToolExecutor: risk gate, schema check, timeout, retry, events."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Dict, List, Optional, Tuple

from metaforge.harness.runtime import AgentRuntime
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool

_TYPE_MAP = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _is_approved(params: Dict[str, Any], ctx: ToolContext) -> bool:
    if params.get("_tool_approved") is True:
        return True
    if bool(params.get("skip_strategy_hitl")):
        return True
    extras = ctx.extras or {}
    if extras.get("tool_approved") is True:
        return True
    if extras.get("confirm_token"):
        return True
    return False


def _validate_against_schema(
    payload: Any, schema: Optional[Dict[str, Any]], *, label: str
) -> Optional[str]:
    if not schema or not isinstance(schema, dict):
        return None
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(payload, dict):
            return f"{label} must be object"
        required = schema.get("required") or []
        for key in required:
            if key not in payload:
                return f"{label} missing required field: {key}"
        props = schema.get("properties") or {}
        for key, prop in props.items():
            if key not in payload or payload[key] is None:
                continue
            if not isinstance(prop, dict):
                continue
            ptype = prop.get("type")
            py = _TYPE_MAP.get(ptype) if isinstance(ptype, str) else None
            if py is not None and not isinstance(payload[key], py):
                # number accepts int
                if ptype == "number" and isinstance(payload[key], bool):
                    return f"{label}.{key} must be number"
                if ptype == "number" and isinstance(payload[key], (int, float)):
                    continue
                if ptype == "integer" and isinstance(payload[key], bool):
                    return f"{label}.{key} must be integer"
                if not isinstance(payload[key], py):
                    return f"{label}.{key} must be {ptype}"
    return None


def _hitl_result(name: str, risk: str) -> ToolResult:
    return ToolResult(
        ok=False,
        error=f"tool requires HITL approval: {name}",
        data={"needs_hitl": True, "tool": name, "risk_level": risk},
    )


def _call_handler(spec: ToolSpec, params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    try:
        return spec.handler(params, ctx)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))


def _execute_once(
    spec: ToolSpec, params: Dict[str, Any], ctx: ToolContext
) -> ToolResult:
    timeout = spec.timeout_seconds
    if timeout is None or timeout <= 0:
        return _call_handler(spec, params, ctx)
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_call_handler, spec, params, ctx)
        try:
            return fut.result(timeout=float(timeout))
        except FuturesTimeout:
            return ToolResult(
                ok=False,
                error=f"tool timeout after {timeout}s: {spec.name}",
                data={"timeout": True, "tool": spec.name},
            )


def _max_retries(spec: ToolSpec) -> int:
    policy = spec.retry_policy or {}
    try:
        return max(0, int(policy.get("max_retries") or 0))
    except (TypeError, ValueError):
        return 0


def execute_tool(
    name: str,
    params: Optional[Dict[str, Any]],
    ctx: Optional[ToolContext] = None,
    *,
    runtime: Optional[AgentRuntime] = None,
    spec: Optional[ToolSpec] = None,
) -> ToolResult:
    """Run a registered tool through the harness executor."""
    ctx = ctx or ToolContext()
    params = dict(params or {})
    runtime = runtime or AgentRuntime()
    try:
        tool_spec = spec or get_tool(name)
    except KeyError:
        runtime.emit("tool.error", payload={"tool": name, "error": "unknown tool"})
        return ToolResult(ok=False, error=f"Unknown tool: {name}")

    risk = (tool_spec.risk_level or "allow").lower()
    runtime.emit(
        "tool.start",
        payload={"tool": name, "risk_level": risk},
    )

    if risk == "deny":
        runtime.emit("tool.denied", payload={"tool": name})
        return ToolResult(
            ok=False,
            error=f"tool denied by policy: {name}",
            data={"risk_level": "deny", "tool": name},
        )

    if risk == "ask" and not _is_approved(params, ctx):
        runtime.emit("tool.needs_hitl", payload={"tool": name})
        return _hitl_result(name, risk)

    # Strip internal flags before handler
    params.pop("_tool_approved", None)

    err = _validate_against_schema(params, tool_spec.input_schema, label="input")
    if err:
        runtime.emit("tool.invalid_input", payload={"tool": name, "error": err})
        return ToolResult(ok=False, error=err, data={"validation": "input"})

    attempts = 1 + _max_retries(tool_spec)
    result: ToolResult = ToolResult(ok=False, error="not executed")
    for i in range(attempts):
        result = _execute_once(tool_spec, params, ctx)
        if result.ok:
            break
        if result.data and result.data.get("timeout") and i + 1 < attempts:
            runtime.emit(
                "tool.retry",
                payload={"tool": name, "attempt": i + 1, "reason": "timeout"},
            )
            continue
        if (not result.ok) and i + 1 < attempts and not (result.data or {}).get("needs_hitl"):
            runtime.emit(
                "tool.retry",
                payload={"tool": name, "attempt": i + 1, "reason": "error"},
            )
            continue
        break

    if result.ok and tool_spec.output_schema:
        out_err = _validate_against_schema(
            result.data, tool_spec.output_schema, label="output"
        )
        if out_err:
            runtime.emit(
                "tool.invalid_output",
                payload={"tool": name, "error": out_err},
            )
            return ToolResult(ok=False, error=out_err, data={"validation": "output"})

    runtime.emit(
        "tool.end",
        payload={
            "tool": name,
            "ok": bool(result.ok),
            "error": result.error,
        },
    )
    return result


def execute_tool_with_events(
    name: str,
    params: Optional[Dict[str, Any]],
    ctx: Optional[ToolContext] = None,
) -> Tuple[ToolResult, List[Dict[str, Any]]]:
    runtime = AgentRuntime()
    result = execute_tool(name, params, ctx, runtime=runtime)
    return result, [e.to_dict() for e in runtime.events]
