"""memory.run — 统一记忆 Tool（对标 Hello-Agents MemoryTool 的 get/set/patch/summary）。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.memory.manager import MemoryManager
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    action = (params.get("action") or "summary").strip().lower()
    session_id = (ctx.extras or {}).get("session_id") or (params.get("session_id") or "")
    mm = MemoryManager(session_id or None, context={"session_id": session_id, "artifacts": ctx.artifacts})

    if action == "get":
        scope = (params.get("scope") or "working").strip().lower()
        if scope == "scheduling":
            data = mm.get_scheduling()
        elif scope == "episodic":
            data = {"episodic": mm.store.get("episodic") or []}
        else:
            ns = str(params.get("namespace") or "")
            key = str(params.get("key") or "")
            if not ns or not key:
                return ToolResult(ok=False, error="working get 需要 namespace 与 key")
            data = mm.get_working(ns, key)
        return ToolResult(ok=True, data=data)

    if action == "set":
        scope = (params.get("scope") or "working").strip().lower()
        value = params.get("value")
        if scope == "scheduling":
            if not isinstance(value, dict):
                return ToolResult(ok=False, error="scheduling set 需要 value 为 object")
            mm.set_scheduling(value)
        else:
            ns = str(params.get("namespace") or "")
            key = str(params.get("key") or "")
            if not ns or not key:
                return ToolResult(ok=False, error="working set 需要 namespace 与 key")
            mm.set_working(ns, key, value)
        return ToolResult(ok=True, data={"ok": True})

    if action == "patch":
        scope = (params.get("scope") or "working").strip().lower()
        patch = params.get("patch") or params.get("value")
        if not isinstance(patch, dict):
            return ToolResult(ok=False, error="patch 需要 patch/value 为 object")
        if scope == "scheduling":
            data = mm.patch_scheduling(patch)
        else:
            ns = str(params.get("namespace") or "")
            key = str(params.get("key") or "")
            if not ns or not key:
                return ToolResult(ok=False, error="working patch 需要 namespace 与 key")
            data = mm.patch_working(ns, key, patch)
        return ToolResult(ok=True, data=data)

    if action == "summary":
        return ToolResult(ok=True, data={"summary_zh": mm.summary_zh(), "store_keys": list((mm.store.get("working") or {}).keys())})

    return ToolResult(ok=False, error=f"未知 action: {action}，支持 get/set/patch/summary")


def register_memory_tool() -> None:
    name = "memory.run"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="会话记忆：get/set/patch/summary（工作记忆/排程记忆）",
            input_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "scope": {"type": "string"},
                    "namespace": {"type": "string"},
                    "key": {"type": "string"},
                    "value": {},
                    "patch": {"type": "object"},
                },
            },
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
