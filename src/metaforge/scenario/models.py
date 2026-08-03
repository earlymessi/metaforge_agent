from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
import uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ScenarioStep:
    event_type: str
    params: dict[str, Any] = field(default_factory=dict)
    t: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"event_type": self.event_type, "params": dict(self.params)}
        if self.t is not None:
            d["t"] = self.t
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ScenarioStep":
        if not isinstance(raw, dict) or not raw.get("event_type"):
            raise ValueError("scenario step requires event_type")
        return cls(
            event_type=str(raw["event_type"]),
            params=dict(raw.get("params") or {}),
            t=raw.get("t"),
        )


@dataclass
class Scenario:
    name: str
    steps: list[ScenarioStep] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    description: str = ""
    preset: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "preset": self.preset,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Scenario":
        if not isinstance(raw, dict) or not raw.get("name"):
            raise ValueError("scenario requires name")
        steps_raw = raw.get("steps") or []
        if not isinstance(steps_raw, list):
            raise ValueError("scenario steps must be a list")
        steps = [ScenarioStep.from_dict(s) for s in steps_raw]
        return cls(
            id=str(raw.get("id") or uuid.uuid4()),
            name=str(raw["name"]),
            description=str(raw.get("description") or ""),
            preset=bool(raw.get("preset", False)),
            steps=steps,
            created_at=str(raw.get("created_at") or _now_iso()),
            updated_at=str(raw.get("updated_at") or _now_iso()),
        )
