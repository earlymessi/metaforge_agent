"""Ensure /api/run keeps FAB fields and evaluates when domain=fab."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_TESTS_DIR = Path(__file__).resolve().parents[1]
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


def test_load_then_run_photo_carries_fab_fields(client):
    loaded = client.post("/api/fab/scenarios/fab_photo_dedication_v1/load").json()
    jobs = loaded["jobs"]
    assert any(
        t.get("process_area") == "photo" for j in jobs for t in j.get("tasks") or []
    )

    payload = {
        "solvers": ["spt"],
        "domain": "fab",
        "scenario_id": loaded["scenario_id"],
        "fab_meta": loaded["fab_meta"],
        "strategy_defaults": loaded["strategy_defaults"],
        "custom_data": jobs,
        "enforce_material": False,
    }
    r = client.post("/api/run", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "success" or "data" in body
    assert body.get("domain") == "fab"
    assert "fab_evaluation" in body
    assert "spt" in (body.get("data") or {})
    assert "fab_hard_ok" in body["data"]["spt"]


def test_classic_run_no_fab_evaluation(client):
    r = client.post(
        "/api/run",
        json={"solvers": ["spt"], "benchmark_file": "ft06.txt"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "fab_evaluation" not in body
