"""Compile-once planning context with stable hash."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from metaforge.strategy.context_builder import build_for_strategy_generation


def _stable_hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class CompiledContext:
    """Single compiled view for planning Preview / Run / LLM prompts."""

    user_goal: str
    orders_summary: List[Dict[str, Any]]
    machines_summary: List[str]
    constraint_catalog_short: List[Dict[str, Any]]
    preset_ids: List[str]
    context_hash: str
    bom_item_count: int = 0
    gantt_op_count: int = 0
    existing_constraints: List[Any] = field(default_factory=list)
    downtime_summary: List[Any] = field(default_factory=list)
    order_analysis: Dict[str, Any] = field(default_factory=dict)
    constraint_analysis: Dict[str, Any] = field(default_factory=dict)
    resource_analysis: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def to_prompt_dict(self) -> Dict[str, Any]:
        """Shape expected by strategy generation (no hash/artifacts)."""
        return {
            "user_goal": self.user_goal,
            "orders_summary": self.orders_summary,
            "machines_summary": self.machines_summary,
            "constraint_catalog_short": self.constraint_catalog_short,
            "preset_ids": self.preset_ids,
            "bom_item_count": self.bom_item_count,
            "gantt_op_count": self.gantt_op_count,
            "existing_constraints": self.existing_constraints,
            "downtime_summary": self.downtime_summary,
            "order_analysis": self.order_analysis,
            "constraint_analysis": self.constraint_analysis,
            "resource_analysis": self.resource_analysis,
        }

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def compile_planning_context(
    *,
    user_goal: str,
    jobs: Optional[Iterable[Any]] = None,
    machines: Optional[Iterable[Any]] = None,
    gantt_data: Any = None,
    bom: Any = None,
    existing_constraints: Optional[List[Any]] = None,
    downtime: Optional[List[Any]] = None,
    order_analysis: Optional[Dict[str, Any]] = None,
    constraint_analysis: Optional[Dict[str, Any]] = None,
    resource_analysis: Optional[Dict[str, Any]] = None,
    artifacts: Optional[Dict[str, Any]] = None,
) -> CompiledContext:
    """Reuse strategy context_builder rules; add stable context_hash."""
    base = build_for_strategy_generation(
        user_goal=user_goal,
        jobs=jobs,
        machines=machines,
        gantt_data=gantt_data,
        bom=bom,
        existing_constraints=existing_constraints,
        downtime=downtime,
        order_analysis=order_analysis,
        constraint_analysis=constraint_analysis,
        resource_analysis=resource_analysis,
    )
    digest = {
        "user_goal": base["user_goal"],
        "orders_summary": base["orders_summary"],
        "machines_summary": base["machines_summary"],
        "constraint_catalog_short": base["constraint_catalog_short"],
        "preset_ids": base["preset_ids"],
        "bom_item_count": base["bom_item_count"],
        "gantt_op_count": base["gantt_op_count"],
        "existing_constraints": base["existing_constraints"],
        "downtime_summary": base["downtime_summary"],
    }
    return CompiledContext(
        user_goal=base["user_goal"],
        orders_summary=base["orders_summary"],
        machines_summary=base["machines_summary"],
        constraint_catalog_short=base["constraint_catalog_short"],
        preset_ids=base["preset_ids"],
        context_hash=_stable_hash(digest),
        bom_item_count=base["bom_item_count"],
        gantt_op_count=base["gantt_op_count"],
        existing_constraints=base["existing_constraints"],
        downtime_summary=base["downtime_summary"],
        order_analysis=base["order_analysis"],
        constraint_analysis=base["constraint_analysis"],
        resource_analysis=base["resource_analysis"],
        artifacts=dict(artifacts or {}),
    )
