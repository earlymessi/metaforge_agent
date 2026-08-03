from __future__ import annotations

from copy import deepcopy
from typing import Any

from metaforge.scenario.models import Scenario, ScenarioStep


def list_preset_scenarios() -> list[dict[str, Any]]:
    """Return builtin disturbance scenario templates (dicts)."""
    return [s.to_dict() for s in _preset_objects()]


def _preset_objects() -> list[Scenario]:
    return [
        Scenario(
            id="preset-machine-breakdown",
            name="设备故障",
            description="单机故障短时停机后重排",
            preset=True,
            steps=[
                ScenarioStep(
                    event_type="machine_breakdown",
                    params={
                        "machine_id": 0,
                        "breakdown_start": 0,
                        "breakdown_duration": 2,
                    },
                )
            ],
        ),
        Scenario(
            id="preset-insert-order",
            name="紧急插单",
            description="插入一笔急单并局部修复",
            preset=True,
            steps=[
                ScenarioStep(
                    event_type="insert_order",
                    params={
                        "insert_job": {
                            "name": "INSERT_URGENT",
                            "priority": 1,
                            "due_date": 10,
                            "ops": [{"machine": 0, "proc": 2}],
                        },
                        "freeze_time": 0,
                        "mode": "local_repair",
                    },
                )
            ],
        ),
        Scenario(
            id="preset-due-date-change",
            name="交期变更",
            description="缩短首单交期并评估影响",
            preset=True,
            steps=[
                ScenarioStep(
                    event_type="due_date_change",
                    params={
                        "due_date_changes": [
                            {"job_name": "J1", "new_due_date": 5},
                        ]
                    },
                )
            ],
        ),
    ]


def clone_preset(preset_id: str) -> dict[str, Any]:
    for p in _preset_objects():
        if p.id == preset_id:
            data = deepcopy(p.to_dict())
            data["preset"] = False
            data.pop("id", None)
            return data
    raise ValueError(f"unknown preset: {preset_id!r}")
