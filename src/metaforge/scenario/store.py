from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from metaforge.scenario.models import Scenario


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScenarioStore:
    """In-process scenario store (dict). Swap for Mongo later without changing callers."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def list(self) -> list[dict[str, Any]]:
        return [dict(v) for v in self._items.values()]

    def get(self, scenario_id: str) -> Optional[dict[str, Any]]:
        item = self._items.get(scenario_id)
        return dict(item) if item else None

    def create(self, raw: dict[str, Any]) -> dict[str, Any]:
        scenario = Scenario.from_dict(raw)
        if not scenario.id:
            scenario.id = str(uuid.uuid4())
        if scenario.id in self._items:
            raise ValueError(f"scenario already exists: {scenario.id}")
        scenario.created_at = _now_iso()
        scenario.updated_at = scenario.created_at
        data = scenario.to_dict()
        self._items[scenario.id] = data
        return dict(data)

    def update(self, scenario_id: str, raw: dict[str, Any]) -> dict[str, Any]:
        if scenario_id not in self._items:
            raise KeyError(scenario_id)
        payload = dict(raw)
        payload["id"] = scenario_id
        if "created_at" not in payload:
            payload["created_at"] = self._items[scenario_id].get("created_at")
        scenario = Scenario.from_dict(payload)
        scenario.updated_at = _now_iso()
        data = scenario.to_dict()
        self._items[scenario_id] = data
        return dict(data)

    def delete(self, scenario_id: str) -> bool:
        return self._items.pop(scenario_id, None) is not None


# Process-wide default store used by API layer.
default_store = ScenarioStore()
