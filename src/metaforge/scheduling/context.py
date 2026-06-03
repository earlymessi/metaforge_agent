"""排程会话记忆：工作记忆（澄清态）+ 语义偏好 + 情景日志；可同步 Orchestrator Session。"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

PENDING_TTL_SECONDS = 3600
_EPISODIC_MAX = 20

# 与澄清文案 ①②③④ 一致
OFFERED_GOAL_OPTIONS: List[Dict[str, Any]] = [
    {
        "option_id": "1",
        "goal_id": "weighted_tardiness_total",
        "strategy_id": "delivery",
        "label_zh": "交期/拖期最少",
        "markers": ["①", "1", "一", "选项1", "选1"],
    },
    {
        "option_id": "2",
        "goal_id": "makespan",
        "strategy_id": "makespan",
        "label_zh": "完工时间最短",
        "markers": ["②", "2", "二", "选项2", "选2"],
    },
    {
        "option_id": "3",
        "goal_id": "energy_cost",
        "strategy_id": "cost",
        "label_zh": "能耗成本最低",
        "markers": ["③", "3", "三", "选项3", "选3"],
    },
    {
        "option_id": "4",
        "goal_id": "machine_busy_cv",
        "strategy_id": "balance_load",
        "label_zh": "负载均衡",
        "markers": ["④", "4", "四", "选项4", "选4"],
    },
]


@dataclass
class ClarificationState:
    """工作记忆：等待用户选定排程业务目标（不拼接进解析用自然语言）。"""

    phase: str = "awaiting_goal_choice"
    original_message: str = ""
    question: str = ""
    unmapped_phrase: Optional[str] = None
    offered_options: List[Dict[str, Any]] = field(default_factory=list)
    created_at_ts: float = 0.0
    expires_at_ts: float = 0.0

    def is_expired(self) -> bool:
        return bool(self.expires_at_ts) and time.time() > self.expires_at_ts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "original_message": self.original_message,
            "question": self.question,
            "unmapped_phrase": self.unmapped_phrase,
            "offered_options": copy.deepcopy(self.offered_options),
            "created_at_ts": self.created_at_ts,
            "expires_at_ts": self.expires_at_ts,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["ClarificationState"]:
        if not data:
            return None
        return cls(
            phase=str(data.get("phase") or "awaiting_goal_choice"),
            original_message=str(data.get("original_message") or ""),
            question=str(data.get("question") or ""),
            unmapped_phrase=data.get("unmapped_phrase"),
            offered_options=list(data.get("offered_options") or OFFERED_GOAL_OPTIONS),
            created_at_ts=float(data.get("created_at_ts") or 0),
            expires_at_ts=float(data.get("expires_at_ts") or 0),
        )


@dataclass
class ScheduleContext:
    """语义记忆 + 工作记忆（pending）+ 情景日志。"""

    last_solvers: List[str] = field(default_factory=list)
    last_strategy_id: str = "balanced"
    default_solvers: List[str] = field(default_factory=list)
    default_strategy_id: str = "balanced"
    enforce_material: bool = True
    last_schedule_goal: str = ""
    last_schedule_goal_name_zh: str = ""
    last_run_summary: str = ""
    pending_clarification: Optional[Dict[str, Any]] = None
    episodic_log: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "last_solvers": list(self.last_solvers),
            "last_strategy_id": self.last_strategy_id,
            "default_solvers": list(self.default_solvers),
            "default_strategy_id": self.default_strategy_id,
            "enforce_material": self.enforce_material,
            "last_schedule_goal": self.last_schedule_goal,
            "last_schedule_goal_name_zh": self.last_schedule_goal_name_zh,
            "last_run_summary": self.last_run_summary,
            "pending_clarification": copy.deepcopy(self.pending_clarification),
            "episodic_log": copy.deepcopy(self.episodic_log),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ScheduleContext":
        if not data:
            return cls()
        return cls(
            last_solvers=list(data.get("last_solvers") or []),
            last_strategy_id=str(data.get("last_strategy_id") or "balanced"),
            default_solvers=list(data.get("default_solvers") or []),
            default_strategy_id=str(data.get("default_strategy_id") or "balanced"),
            enforce_material=bool(data.get("enforce_material", True)),
            last_schedule_goal=str(data.get("last_schedule_goal") or ""),
            last_schedule_goal_name_zh=str(data.get("last_schedule_goal_name_zh") or ""),
            last_run_summary=str(data.get("last_run_summary") or ""),
            pending_clarification=data.get("pending_clarification"),
            episodic_log=list(data.get("episodic_log") or []),
        )


class ContextManager:
    _store: Dict[str, ScheduleContext] = {}

    @classmethod
    def _key(cls, session_id: Optional[str]) -> str:
        return (session_id or "").strip() or "default"

    @classmethod
    def _load_from_orchestrator_session(cls, session_id: Optional[str]) -> Optional[ScheduleContext]:
        if not session_id or session_id == "default":
            return None
        try:
            from metaforge.orchestrator.session import get_scheduling_memory

            raw = get_scheduling_memory(session_id)
            if raw:
                return ScheduleContext.from_dict(raw)
        except Exception:
            pass
        return None

    @classmethod
    def _persist_to_orchestrator_session(cls, session_id: Optional[str], ctx: ScheduleContext) -> None:
        if not session_id or session_id == "default":
            return
        try:
            from metaforge.orchestrator.session import set_scheduling_memory

            set_scheduling_memory(session_id, ctx.to_dict())
        except Exception:
            pass

    @classmethod
    def get(cls, session_id: Optional[str] = None) -> ScheduleContext:
        key = cls._key(session_id)
        if key not in cls._store:
            loaded = cls._load_from_orchestrator_session(session_id)
            cls._store[key] = loaded if loaded else ScheduleContext()
        return cls._store[key]

    @classmethod
    def save(cls, session_id: Optional[str], ctx: ScheduleContext) -> None:
        cls._store[cls._key(session_id)] = ctx
        cls._persist_to_orchestrator_session(session_id, ctx)

    @classmethod
    def clear_session(cls, session_id: Optional[str] = None) -> None:
        cls._store.pop(cls._key(session_id), None)

    @classmethod
    def get_clarification(cls, session_id: Optional[str]) -> Optional[ClarificationState]:
        ctx = cls.get(session_id)
        state = ClarificationState.from_dict(ctx.pending_clarification)
        if state and state.is_expired():
            cls.clear_pending(session_id)
            return None
        return state

    @classmethod
    def get_pending(cls, session_id: Optional[str]) -> Optional[Dict[str, Any]]:
        state = cls.get_clarification(session_id)
        return state.to_dict() if state else None

    @classmethod
    def set_clarification(
        cls,
        session_id: Optional[str],
        *,
        original_message: str,
        question: str,
        unmapped_phrase: Optional[str] = None,
        partial_intent: Optional[Dict[str, Any]] = None,
    ) -> ClarificationState:
        now = time.time()
        state = ClarificationState(
            phase="awaiting_goal_choice",
            original_message=(original_message or "").strip(),
            question=(question or "").strip(),
            unmapped_phrase=unmapped_phrase,
            offered_options=copy.deepcopy(OFFERED_GOAL_OPTIONS),
            created_at_ts=now,
            expires_at_ts=now + PENDING_TTL_SECONDS,
        )
        ctx = cls.get(session_id)
        ctx.pending_clarification = state.to_dict()
        cls._append_episode(
            ctx,
            "clarification_requested",
            summary=question[:200],
            extra={
                "unmapped_phrase": unmapped_phrase,
                "partial": partial_intent or {},
            },
        )
        cls.save(session_id, ctx)
        return state

    @classmethod
    def set_pending(
        cls,
        session_id: Optional[str],
        *,
        original_message: str,
        partial_intent: Dict[str, Any],
        question: str,
    ) -> None:
        unmapped = (partial_intent or {}).get("unmapped_phrase")
        if not unmapped and isinstance(partial_intent, dict):
            unmapped = partial_intent.get("partial", {}).get("unmapped_phrase")
        cls.set_clarification(
            session_id,
            original_message=original_message,
            question=question,
            unmapped_phrase=unmapped,
            partial_intent=partial_intent,
        )

    @classmethod
    def clear_pending(cls, session_id: Optional[str]) -> None:
        ctx = cls.get(session_id)
        ctx.pending_clarification = None
        cls.save(session_id, ctx)

    @classmethod
    def retrieve(cls, session_id: Optional[str] = None) -> Dict[str, Any]:
        """检索式上下文（替代字符串 merge）。"""
        ctx = cls.get(session_id)
        clar = cls.get_clarification(session_id)
        return {
            "preferences": {
                "last_solvers": list(ctx.last_solvers),
                "last_strategy_id": ctx.last_strategy_id,
                "default_strategy_id": ctx.default_strategy_id,
                "default_solvers": list(ctx.default_solvers),
                "enforce_material": ctx.enforce_material,
                "last_schedule_goal": ctx.last_schedule_goal,
                "last_schedule_goal_name_zh": ctx.last_schedule_goal_name_zh,
            },
            "pending_clarification": clar.to_dict() if clar else None,
            "episodic_recent": list(ctx.episodic_log[-5:]),
            "has_pending": clar is not None,
        }

    @classmethod
    def merge_clarification_reply(cls, session_id: Optional[str], reply: str) -> str:
        """兼容旧路径：仍拼接全文；新逻辑应优先 parse_clarification_reply + 结构化 pending。"""
        pending = cls.get_pending(session_id)
        if not pending:
            return (reply or "").strip()
        original = (pending.get("original_message") or "").strip()
        reply = (reply or "").strip()
        if original and reply:
            return f"{original}；{reply}"
        return original or reply

    @classmethod
    def to_llm_context(cls, session_id: Optional[str] = None) -> Dict[str, Any]:
        mem = cls.retrieve(session_id)
        prefs = mem.get("preferences") or {}
        out = {
            "last_solvers": prefs.get("last_solvers") or [],
            "last_strategy_id": prefs.get("last_strategy_id") or "balanced",
            "default_strategy_id": prefs.get("default_strategy_id") or "balanced",
            "default_solvers": prefs.get("default_solvers") or [],
            "enforce_material": prefs.get("enforce_material", True),
            "last_schedule_goal": prefs.get("last_schedule_goal") or "",
        }
        if mem.get("has_pending"):
            out["pending_clarification"] = mem.get("pending_clarification")
        return out

    @classmethod
    def _append_episode(
        cls,
        ctx: ScheduleContext,
        event_type: str,
        *,
        summary: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        ctx.episodic_log.append(
            {
                "type": event_type,
                "ts": time.time(),
                "summary": summary[:300],
                **(extra or {}),
            }
        )
        if len(ctx.episodic_log) > _EPISODIC_MAX:
            ctx.episodic_log = ctx.episodic_log[-_EPISODIC_MAX:]

    @classmethod
    def update_from_interpretation(
        cls, session_id: Optional[str], data: Dict[str, Any]
    ) -> None:
        ctx = cls.get(session_id)
        itype = str(data.get("intent_type") or "")
        if itype in ("SET_DEFAULT_STRATEGY",) and data.get("strategy_id"):
            ctx.default_strategy_id = str(data["strategy_id"])
        if itype in ("SET_DEFAULT_SOLVER",) and data.get("solvers"):
            ctx.default_solvers = list(data["solvers"])
        if data.get("enforce_material") is not None and itype in (
            "RUN_SCHEDULE",
            "COMPARE_SOLVERS",
            "RUN_BENCHMARK",
            "TOGGLE_MATERIAL",
        ):
            ctx.enforce_material = bool(data["enforce_material"])
        if data.get("solvers") and itype in (
            "RUN_SCHEDULE",
            "COMPARE_SOLVERS",
            "RUN_BENCHMARK",
        ):
            ctx.last_solvers = list(data["solvers"])
        if data.get("strategy_id") and itype in (
            "RUN_SCHEDULE",
            "COMPARE_SOLVERS",
            "RUN_BENCHMARK",
        ):
            ctx.last_strategy_id = str(data["strategy_id"])
            ctx.default_strategy_id = str(data["strategy_id"])
        if data.get("schedule_goal"):
            ctx.last_schedule_goal = str(data["schedule_goal"])
        if data.get("schedule_goal_name_zh"):
            ctx.last_schedule_goal_name_zh = str(data["schedule_goal_name_zh"])
        if data.get("summary_zh"):
            ctx.last_run_summary = str(data["summary_zh"])[:500]
        cls.save(session_id, ctx)

    @classmethod
    def consolidate_after_run(
        cls,
        session_id: Optional[str],
        data: Dict[str, Any],
        *,
        event_type: str = "schedule_completed",
    ) -> None:
        """工作记忆固化：清除 pending，写入语义偏好与情景日志。"""
        ctx = cls.get(session_id)
        had_pending = ctx.pending_clarification is not None
        pending_snap = copy.deepcopy(ctx.pending_clarification)
        ctx.pending_clarification = None
        cls.update_from_interpretation(session_id, data)
        ctx = cls.get(session_id)
        summary = str(data.get("summary_zh") or ctx.last_run_summary or "")[:200]
        cls._append_episode(
            ctx,
            event_type,
            summary=summary,
            extra={
                "strategy_id": data.get("strategy_id"),
                "schedule_goal": data.get("schedule_goal"),
                "full_compare": data.get("full_compare"),
                "resolved_from_clarification": had_pending,
                "prior_unmapped": (pending_snap or {}).get("unmapped_phrase"),
            },
        )
        cls.save(session_id, ctx)
