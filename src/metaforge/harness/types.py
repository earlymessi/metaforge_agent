"""Harness shared types: RunEvent and compiled-run placeholders."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import time
from typing import Any, Dict, List, Optional


@dataclass
class RunEvent:
    """One observability event in a harness run."""

    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    agent_id: Optional[str] = None
    ts: float = field(default_factory=time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CompiledRun:
    """Compile-once handle for a planning request (filled in later phases)."""

    run_id: str
    skill_id: Optional[str] = None
    context_hash: Optional[str] = None
    events: List[RunEvent] = field(default_factory=list)
