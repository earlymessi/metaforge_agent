from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Constraint:
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    penalty: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"type": self.type, **self.params}
        if self.penalty is not None:
            d["penalty"] = self.penalty
        return d


@dataclass
class SchedulingStrategy:
    strategy_id: Optional[str] = None
    base_template: Optional[str] = None
    objectives: Dict[str, float] = field(default_factory=dict)
    hard_constraints: List[Constraint] = field(default_factory=list)
    soft_constraints: List[Constraint] = field(default_factory=list)
    critical_orders: List[str] = field(default_factory=list)
    machine_preferences: Dict[str, Any] = field(default_factory=dict)
    machine_limits: Dict[str, Any] = field(default_factory=dict)
    overtime_policy: Optional[Dict[str, Any]] = None
    freeze_policy: Optional[Dict[str, Any]] = None
    solver_preferences: Optional[Dict[str, Any]] = None
    generated_by: str = "user"
    explanation: str = ""
    provenance: Dict[str, Any] = field(default_factory=lambda: {"simulated_fields": []})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "base_template": self.base_template,
            "objectives": dict(self.objectives),
            "hard_constraints": [c.to_dict() for c in self.hard_constraints],
            "soft_constraints": [c.to_dict() for c in self.soft_constraints],
            "critical_orders": list(self.critical_orders),
            "machine_preferences": dict(self.machine_preferences),
            "machine_limits": dict(self.machine_limits),
            "overtime_policy": self.overtime_policy,
            "freeze_policy": self.freeze_policy,
            "solver_preferences": self.solver_preferences,
            "generated_by": self.generated_by,
            "explanation": self.explanation,
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SchedulingStrategy":
        def _parse_constraints(items: Any) -> List[Constraint]:
            out: List[Constraint] = []
            for raw in items or []:
                if not isinstance(raw, dict):
                    continue
                t = str(raw.get("type") or "")
                penalty = raw.get("penalty")
                params = {k: v for k, v in raw.items() if k not in ("type", "penalty")}
                out.append(Constraint(type=t, params=params, penalty=penalty))
            return out

        return cls(
            strategy_id=data.get("strategy_id"),
            base_template=data.get("base_template"),
            objectives={k: float(v) for k, v in (data.get("objectives") or {}).items()},
            hard_constraints=_parse_constraints(data.get("hard_constraints")),
            soft_constraints=_parse_constraints(data.get("soft_constraints")),
            critical_orders=list(data.get("critical_orders") or []),
            machine_preferences=dict(data.get("machine_preferences") or {}),
            machine_limits=dict(data.get("machine_limits") or {}),
            overtime_policy=data.get("overtime_policy"),
            freeze_policy=data.get("freeze_policy"),
            solver_preferences=data.get("solver_preferences"),
            generated_by=str(data.get("generated_by") or "user"),
            explanation=str(data.get("explanation") or ""),
            provenance=dict(data.get("provenance") or {"simulated_fields": []}),
        )
