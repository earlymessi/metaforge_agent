import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PLANNING_STRATEGY_V1", "1")
    from main import app

    return TestClient(app)


def test_planning_presets_ok(client):
    r = client.get("/api/planning/strategy/presets")
    assert r.status_code == 200
    assert len(r.json()["presets"]) >= 6


def test_planning_disabled_returns_404(monkeypatch):
    monkeypatch.setenv("PLANNING_STRATEGY_V1", "0")
    from main import app

    client = TestClient(app)
    r = client.get("/api/planning/strategy/presets")
    assert r.status_code == 404


def test_planning_run_skip_hitl(client, monkeypatch):
    def fake_run_planning(**kwargs):
        return {
            "status": "COMPLETED",
            "run_id": "r-test",
            "package": {"recommended_schedule_id": "ts"},
        }

    monkeypatch.setattr("metaforge.strategy.pipeline.run_planning", fake_run_planning)
    r = client.post(
        "/api/planning/run",
        json={
            "user_goal": "综合平衡排程",
            "jobs": [{"job_id": "J1", "priority": 1}],
            "machines": ["M01"],
            "skip_strategy_hitl": True,
        },
    )
    assert r.status_code in (200, 202)
    body = r.json()
    assert body.get("run_id") or body.get("package")
