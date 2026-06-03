"""MemoryManager：会话级统一读写，避免各 Agent 自建记忆机制。"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional, Tuple

from metaforge.memory.types import (
    ARTIFACT_ALIASES,
    WORKING_KEY_INSERT_JOB,
    empty_memory_store,
    working_key,
)


def _session_id_from(context: Optional[Dict[str, Any]]) -> Optional[str]:
    if not context:
        return None
    return (context.get("session_id") or "").strip() or None


def _load_store(session_id: Optional[str], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """优先 context 内嵌 memory_store，否则读 orchestrator session。"""
    if context and isinstance(context.get("memory_store"), dict):
        base = empty_memory_store()
        raw = context["memory_store"]
        base["working"] = dict(raw.get("working") or {})
        base["scheduling"] = dict(raw.get("scheduling") or {}) if raw.get("scheduling") else {}
        base["episodic"] = list(raw.get("episodic") or [])
        return base

    if not session_id:
        return empty_memory_store()

    from metaforge.orchestrator.session import get_memory_store

    store = get_memory_store(session_id)
    if not store:
        # 兼容旧字段 scheduling_memory
        from metaforge.orchestrator.session import get_scheduling_memory

        sched = get_scheduling_memory(session_id)
        store = empty_memory_store()
        if sched:
            store["scheduling"] = dict(sched)
        return store
    return store


def _save_store(session_id: Optional[str], store: Dict[str, Any], context: Optional[Dict[str, Any]]) -> None:
    if context is not None:
        context["memory_store"] = copy.deepcopy(store)

    if not session_id:
        return

    from metaforge.orchestrator.session import set_memory_store

    set_memory_store(session_id, store)
    # 双写兼容旧 API
    sched = store.get("scheduling")
    if isinstance(sched, dict) and sched:
        from metaforge.orchestrator.session import set_scheduling_memory

        set_scheduling_memory(session_id, sched)


def _merge_artifacts_into_store(store: Dict[str, Any], artifacts: Optional[Dict[str, Any]]) -> None:
    arts = artifacts or {}
    for (ns, key), art_key in ARTIFACT_ALIASES.items():
        if art_key in arts and arts[art_key] is not None:
            store.setdefault("working", {})[working_key(ns, key)] = copy.deepcopy(arts[art_key])


class MemoryManager:
    """单会话记忆门面：工作记忆 + 排程语义记忆 + 情景列表。"""

    def __init__(
        self,
        session_id: Optional[str] = None,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.session_id = session_id or _session_id_from(context)
        self._context = context
        self._store = _load_store(self.session_id, context)
        if context and context.get("artifacts"):
            _merge_artifacts_into_store(self._store, context.get("artifacts"))

    @classmethod
    def from_context(cls, context: Optional[Dict[str, Any]]) -> "MemoryManager":
        return cls(_session_id_from(context), context=context)

    @property
    def store(self) -> Dict[str, Any]:
        return self._store

    def flush(self) -> None:
        _save_store(self.session_id, self._store, self._context)

    # --- working ---
    def get_working(self, namespace: str, key: str) -> Any:
        return self._store.get("working", {}).get(working_key(namespace, key))

    def set_working(self, namespace: str, key: str, value: Any) -> None:
        self._store.setdefault("working", {})[working_key(namespace, key)] = copy.deepcopy(value)
        self.flush()

    def patch_working(self, namespace: str, key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        wk = working_key(namespace, key)
        cur = self._store.setdefault("working", {}).get(wk)
        if not isinstance(cur, dict):
            cur = {}
        merged = {**cur, **patch}
        self._store["working"][wk] = merged
        self.flush()
        return merged

    # --- scheduling (semantic + pending clarification) ---
    def get_scheduling(self) -> Dict[str, Any]:
        raw = self._store.get("scheduling")
        return dict(raw) if isinstance(raw, dict) else {}

    def set_scheduling(self, data: Dict[str, Any]) -> None:
        self._store["scheduling"] = copy.deepcopy(data)
        self.flush()

    def patch_scheduling(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        cur = self.get_scheduling()
        merged = {**cur, **patch}
        self.set_scheduling(merged)
        return merged

    # --- episodic ---
    def append_episode(self, item: Dict[str, Any], *, max_items: int = 20) -> None:
        log = self._store.setdefault("episodic", [])
        log.append(copy.deepcopy(item))
        if len(log) > max_items:
            self._store["episodic"] = log[-max_items:]
        self.flush()

    def summary_zh(self) -> str:
        w = self._store.get("working") or {}
        s = self.get_scheduling()
        lines = [f"工作记忆 {len(w)} 条", f"排程记忆 {'有' if s else '无'}"]
        pending = s.get("pending_clarification")
        if pending:
            lines.append("待澄清排程目标")
        intake = self.get_working(*WORKING_KEY_INSERT_JOB)
        if isinstance(intake, dict) and intake.get("status") == "need_input":
            lines.append("待补全插单工艺")
        return "；".join(lines)

    def hydrate_artifacts(self, artifacts: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """工作记忆 → artifacts 兼容字段（Tool 链无需改动即可读到）。"""
        out = dict(artifacts or {})
        for (ns, key), art_key in ARTIFACT_ALIASES.items():
            val = self.get_working(ns, key)
            if val is not None:
                out[art_key] = copy.deepcopy(val)
        return out

    def absorb_artifacts(self, artifacts: Optional[Dict[str, Any]]) -> None:
        """artifacts 回写工作记忆。"""
        arts = artifacts or {}
        for (ns, key), art_key in ARTIFACT_ALIASES.items():
            if art_key in arts and arts[art_key] is not None:
                self.set_working(ns, key, arts[art_key])
        changed = False
        if "scheduling_memory" in arts and isinstance(arts["scheduling_memory"], dict):
            self._store["scheduling"] = copy.deepcopy(arts["scheduling_memory"])
            changed = True
        if changed:
            self.flush()


def sync_context_memory(context: Dict[str, Any]) -> Dict[str, Any]:
    """请求入口：加载 session 记忆并注入 artifacts。"""
    mm = MemoryManager.from_context(context)
    arts = mm.hydrate_artifacts(context.get("artifacts"))
    context["artifacts"] = arts
    context["memory_store"] = mm.store
    return context


def persist_context_memory(
    session_id: Optional[str],
    request_context: Dict[str, Any],
    response: Dict[str, Any],
) -> None:
    """运行结束：artifacts / 排程记忆写回 MemoryManager。"""
    sid = session_id or _session_id_from(request_context)
    mm = MemoryManager(sid, context=request_context)
    mm.absorb_artifacts(response.get("artifacts"))
    mm.absorb_artifacts(request_context.get("artifacts"))
    # ContextManager 可能已写 scheduling 子集
    if isinstance(request_context.get("memory_store"), dict):
        sched = (request_context["memory_store"] or {}).get("scheduling")
        if isinstance(sched, dict) and sched:
            mm._store["scheduling"] = copy.deepcopy(sched)
            mm.flush()
