"""FAB loader/API isolation from classic JSSP benchmarks."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_TESTS_DIR = Path(__file__).resolve().parents[1]
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from main import app  # noqa: E402

FAB_SCENARIO_IDS = {
    "fab_photo_dedication_v1",
    "fab_etch_timelink_v1",
    "fab_diffusion_batch_v1",
}


@pytest.fixture
def client():
    return TestClient(app)


def test_list_fab_scenarios_returns_three_ids(client):
    r = client.get("/api/fab/scenarios")
    assert r.status_code == 200
    scenarios = r.json()["scenarios"]
    ids = {s["scenario_id"] for s in scenarios}
    assert ids == FAB_SCENARIO_IDS


def test_load_fab_scenario_returns_planning_payload(client):
    r = client.post("/api/fab/scenarios/fab_photo_dedication_v1/load")
    assert r.status_code == 200
    body = r.json()
    assert body["domain"] == "fab"
    assert body["scenario_id"] == "fab_photo_dedication_v1"
    assert body["jobs"]
    assert body["strategy_defaults"]["hard_constraints"]
    assert body["fab_meta"]["machine_id_map"]


def test_get_fab_scenario_detail(client):
    r = client.get("/api/fab/scenarios/fab_etch_timelink_v1")
    assert r.status_code == 200
    body = r.json()
    assert body["scenario_id"] == "fab_etch_timelink_v1"
    assert body["domain"] == "fab"


def test_get_fab_scenario_missing_404(client):
    r = client.get("/api/fab/scenarios/does_not_exist")
    assert r.status_code == 404


def test_benchmarks_list_excludes_fab_scenarios(client):
    r = client.get("/api/benchmarks")
    assert r.status_code == 200
    files = r.json()["files"]
    assert files
    assert all(f.endswith(".txt") for f in files)
    fab_stems = {sid.replace("_v1", "") for sid in FAB_SCENARIO_IDS}
    for f in files:
        stem = Path(f).stem
        assert stem not in FAB_SCENARIO_IDS
        assert not stem.startswith("fab_")
        assert stem not in fab_stems
