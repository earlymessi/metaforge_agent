"""Tool 注册表与统一执行入口。"""

from __future__ import annotations

from typing import Any, Dict, List

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec

_TOOL_REGISTRY: Dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> ToolSpec:
    if spec.name in _TOOL_REGISTRY:
        raise ValueError(f"Tool already registered: {spec.name}")
    _TOOL_REGISTRY[spec.name] = spec
    return spec


def get_tool(name: str) -> ToolSpec:
    if name not in _TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: {name}")
    return _TOOL_REGISTRY[name]


def list_tools() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for spec in sorted(_TOOL_REGISTRY.values(), key=lambda s: s.name):
        entry: Dict[str, Any] = {
            "name": spec.name,
            "description_zh": spec.description_zh,
            "input_schema": spec.input_schema,
            "output_schema": spec.output_schema,
        }
        if spec.timeout_seconds is not None:
            entry["timeout_seconds"] = spec.timeout_seconds
        if spec.retry_policy is not None:
            entry["retry_policy"] = spec.retry_policy
        if spec.risk_level != "allow":
            entry["risk_level"] = spec.risk_level
        if spec.idempotency_key_fields is not None:
            entry["idempotency_key_fields"] = spec.idempotency_key_fields
        if spec.permission is not None:
            entry["permission"] = spec.permission
        out.append(entry)
    return out


def run_tool(name: str, params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    spec = get_tool(name)
    try:
        return spec.handler(params or {}, ctx)
    except Exception as e:
        return ToolResult(ok=False, error=str(e))
