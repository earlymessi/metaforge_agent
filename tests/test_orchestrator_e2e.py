"""Orchestrator E2E：intent 路由 + session 续跑。"""

import pytest
from fastapi.testclient import TestClient

from metaforge.orchestrator.router import resolve_agent_id
from metaforge.orchestrator.session import clear_all_sessions
from metaforge.tools.load_all import load_all_tools

MIN_JOBS = [
    {
        "name": "E2E-工单",
        "priority": 10,
        "due_date": 12.0,
        "tasks": [{"machine_id": 0, "duration": 2}, {"machine_id": 1, "duration": 2}],
    }
]

INTENT_AGENT_PARAMS = [
    ("schedule", "scheduling", {"skip_parse": True, "solvers": ["spt"]}),
    ("kitting", "kitting", {"mode": "check_only"}),
    (
        "reschedule",
        "events",
        {
            "skip_parse": True,
            "event_envelope": {
                "event_type": "priority_change",
                "base_jobs": MIN_JOBS,
                "params": {"changes": [{"job_name": "E2E-工单", "new_priority": 50}]},
                "reschedule_options": {"solvers": ["spt"]},
            },
        },
    ),
    ("whatif", "whatif", {"solvers": ["spt"], "strategy_ids": ["delivery", "throughput"]}),
]


def setup_module():
    load_all_tools()
    clear_all_sessions()


def teardown_module():
    clear_all_sessions()


def _client():
    from main import app

    return TestClient(app)


def test_router_keywords_match_agents():
    """LLM 关闭时规则回退覆盖各 Agent 硬边界关键词。"""
    cases = [
        ("用禁忌搜索排程", "scheduling"),
        ("3号机坏了重排", "events"),
        ("新建计划试产01", "plans"),
        ("把这个计划排程并保存落库", "scheduling"),
        ("检查一下齐套能否开工", "kitting"),
        ("交期能不能满足客户", "commitment"),
        ("对比一下交付优先和吞吐优先", "whatif"),
    ]
    for msg, expected in cases:
        assert resolve_agent_id(msg) == expected


def test_get_session_route():
    c = _client()
    r = c.get("/api/orchestrator/session/not-exist")
    assert r.status_code == 404


@pytest.mark.parametrize("intent,expected_agent,params", INTENT_AGENT_PARAMS)
def test_orchestrator_intent_runs(intent, expected_agent, params):
    c = _client()
    body = {
        "intent": intent,
        "context": {"custom_data": MIN_JOBS},
        "params": params,
    }
    if intent == "kitting":
        body["context"]["extras"] = {
            "inventory": {"MAT_A": 999.0},
            "material_names": {"MAT_A": "物料A"},
        }
    r = c.post("/api/orchestrator/run", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("agent_id") == expected_agent
    assert data.get("session_id")
    assert data.get("status") in ("success", "pending_confirm")


def test_orchestrator_session_resume_commitment():
    c = _client()
    r1 = c.post(
        "/api/orchestrator/run",
        json={
            "intent": "schedule",
            "context": {"custom_data": MIN_JOBS},
            "params": {"skip_parse": True, "solvers": ["spt"]},
        },
    )
    assert r1.status_code == 200
    sid = r1.json().get("session_id")
    assert sid
    assert r1.json().get("artifacts", {}).get("schedule_results")

    r2 = c.post(
        "/api/orchestrator/run",
        json={
            "intent": "commitment",
            "context": {"session_id": sid},
            "params": {},
        },
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data.get("agent_id") == "commitment"
    assert data.get("session_id") == sid
    assert data.get("artifacts", {}).get("delivery_assessment")
