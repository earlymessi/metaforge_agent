from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FabScenarioPack:
    schema_version: str
    scenario_id: str
    domain: str
    area: str
    title: str
    physics_refs: List[str] = field(default_factory=list)
    out_of_scope: List[str] = field(default_factory=list)
    entities: Dict[str, Any] = field(default_factory=dict)
    constraints_hard: List[Dict[str, Any]] = field(default_factory=list)
    constraints_soft: List[Dict[str, Any]] = field(default_factory=list)
    objectives_default: Dict[str, Any] = field(default_factory=dict)
    solver_hint: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "domain": self.domain,
            "area": self.area,
            "title": self.title,
            "physics_refs": list(self.physics_refs),
            "out_of_scope": list(self.out_of_scope),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FabScenarioPack":
        objs = data.get("objectives_default") or {}
        if isinstance(objs, list):
            # allow physics-draft list form; map to unit weights
            objs = {str(x).replace("minimize_", "").replace("maximize_", ""): 1.0 for x in objs}
        return cls(
            schema_version=str(data.get("schema_version") or "1"),
            scenario_id=str(data.get("scenario_id") or ""),
            domain=str(data.get("domain") or ""),
            area=str(data.get("area") or ""),
            title=str(data.get("title") or data.get("scenario_id") or ""),
            physics_refs=list(data.get("physics_refs") or []),
            out_of_scope=list(data.get("out_of_scope") or []),
            entities=dict(data.get("entities") or {}),
            constraints_hard=[dict(x) for x in (data.get("constraints_hard") or []) if isinstance(x, dict)],
            constraints_soft=[dict(x) for x in (data.get("constraints_soft") or []) if isinstance(x, dict)],
            objectives_default=dict(objs) if isinstance(objs, dict) else {},
            solver_hint=dict(data["solver_hint"]) if isinstance(data.get("solver_hint"), dict) else None,
            raw=dict(data),
        )
