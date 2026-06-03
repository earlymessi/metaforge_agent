"""events 信封解析（GLM + 规则）测试。"""

import os
import pytest
from unittest.mock import patch

from metaforge.events.resolve_event import resolve_event_envelope
from metaforge.events.llm_event import normalize_llm_event_payload
from metaforge.tools.events.parse_event import parse_event_message


def _jobs():
    return [
        {"name": "工单A", "priority": 10, "tasks": [{"machine_id": 0, "duration": 2}]},
        {"name": "工单B", "priority": 20, "tasks": [{"machine_id": 1, "duration": 3}]},
    ]


@pytest.fixture(autouse=True)
def _clear_llm_env():
    os.environ.pop("LLM_ENABLED", None)
    os.environ.pop("ZHIPU_API_KEY", None)
    yield


def test_resolve_event_rule():
    os.environ["LLM_ENABLED"] = "0"
    env = resolve_event_envelope("3号机坏了4小时", base_jobs=_jobs())
    assert env["planner"] == "rule"
    assert env["event_type"] == "machine_breakdown"


def test_normalize_llm_breakdown():
    raw = {
        "event_type": "machine_breakdown",
        "params": {"machine_id": 2, "breakdown_duration": 6},
        "summary_zh": "故障",
    }
    env = normalize_llm_event_payload(raw, message="x", base_jobs=_jobs())
    assert env["event_type"] == "machine_breakdown"
    assert env["params"]["machine_id"] == 2
    assert env["planner"] == "llm"


@patch("metaforge.events.llm_event.invoke")
def test_resolve_event_llm(mock_invoke):
    mock_invoke.return_value = {
        "event_type": "planned_downtime",
        "base_jobs": _jobs(),
        "params": {
            "downtime_blocks": [{"machine_id": 0, "start": 0, "end": 8, "label": "planned"}]
        },
        "reschedule_options": {},
        "summary_zh": "计划停机",
        "planner": "llm",
    }
    os.environ["LLM_ENABLED"] = "1"
    os.environ["ZHIPU_API_KEY"] = "test"
    env = resolve_event_envelope("1号机停机大修8小时", base_jobs=_jobs())
    assert env["planner"] == "llm"
    assert env["event_type"] == "planned_downtime"


@patch("metaforge.events.llm_event.invoke", side_effect=RuntimeError("401"))
def test_resolve_event_fallback(mock_invoke):
    os.environ["LLM_ENABLED"] = "1"
    os.environ["ZHIPU_API_KEY"] = "test"
    os.environ["LLM_FALLBACK"] = "rule"
    env = resolve_event_envelope("紧急插单", base_jobs=_jobs())
    assert env["planner"] == "rule_fallback"
    assert env["event_type"] == parse_event_message("紧急插单", base_jobs=_jobs())["event_type"]
