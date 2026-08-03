import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PLANNING_COLLAB_V1", "1")
    monkeypatch.setenv("PLANNING_STRATEGY_V1", "1")
    from main import app

    return TestClient(app)


def test_collab_analyze_ok(client):
    r = client.post(
        "/api/planning/collab/analyze",
        json={
            "user_goal": "保证A按期，减少换型",
            "jobs": [
                {
                    "job_id": "A",
                    "due_date": 10,
                    "priority": 8,
                    "tasks": [{"machine_id": 0, "duration": 2}],
                }
            ],
            "machines": ["0"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    arts = body["artifacts"]
    assert "order_analysis" in arts
    assert "constraint_analysis" in arts
    assert "resource_analysis" in arts


def test_collab_run_skip_hitl(client, monkeypatch):
    def fake_run_collab(**kwargs):
        return {
            "status": "COMPLETED",
            "run_id": "plan-1",
            "collab_run_id": "collab-1",
            "package": {"recommended_schedule_id": "edd"},
            "artifacts": {
                "order_analysis": {"critical_orders": []},
                "constraint_analysis": {},
                "resource_analysis": {},
            },
        }

    monkeypatch.setattr(
        "metaforge.planning_collab.supervisor.run_collab", fake_run_collab
    )
    r = client.post(
        "/api/planning/collab/run",
        json={
            "user_goal": "综合平衡",
            "jobs": [{"job_id": "A", "due_date": 20}],
            "machines": ["0"],
            "skip_strategy_hitl": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "COMPLETED"


def test_collab_disabled_returns_404(monkeypatch):
    monkeypatch.setenv("PLANNING_COLLAB_V1", "0")
    from main import app

    client = TestClient(app)
    r = client.post(
        "/api/planning/collab/analyze",
        json={"user_goal": "x", "jobs": []},
    )
    assert r.status_code == 404


def test_collab_get_run(client):
    analyze = client.post(
        "/api/planning/collab/analyze",
        json={
            "user_goal": "综合平衡",
            "jobs": [{"job_id": "A", "tasks": [{"machine_id": 0, "duration": 1}]}],
            "machines": ["0"],
        },
    )
    assert analyze.status_code == 200
    run_id = analyze.json()["run_id"]
    r = client.get(f"/api/planning/collab/runs/{run_id}")
    assert r.status_code == 200
    assert "artifacts" in r.json()
