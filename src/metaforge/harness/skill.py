"""Trusted Skill registry — pack entrypoints under Harness governance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

SkillEntrypoint = Callable[..., Dict[str, Any]]


@dataclass
class SkillSpec:
    id: str
    name_zh: str
    entrypoint: SkillEntrypoint
    allowed_tools: List[str] = field(default_factory=list)
    risk_level: str = "allow"  # allow | ask | deny
    description_zh: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("entrypoint", None)
        return d


_REGISTRY: Dict[str, SkillSpec] = {}


def register_skill(spec: SkillSpec) -> SkillSpec:
    if not spec.id:
        raise ValueError("SkillSpec.id is required")
    _REGISTRY[spec.id] = spec
    return spec


def get_skill(skill_id: str) -> SkillSpec:
    try:
        return _REGISTRY[skill_id]
    except KeyError as exc:
        raise KeyError(f"unknown skill: {skill_id}") from exc


def list_skills() -> List[Dict[str, Any]]:
    return [s.to_dict() for s in _REGISTRY.values()]


def clear_skills() -> None:
    """Test helper."""
    _REGISTRY.clear()


def invoke_skill(skill_id: str, **kwargs: Any) -> Dict[str, Any]:
    spec = get_skill(skill_id)
    out = spec.entrypoint(**kwargs)
    if not isinstance(out, dict):
        raise TypeError(f"skill {skill_id} must return dict")
    result = dict(out)
    result.setdefault("skill_id", skill_id)
    result.setdefault("skill_risk_level", spec.risk_level)
    return result
