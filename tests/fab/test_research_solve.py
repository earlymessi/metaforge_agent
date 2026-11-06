import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from metaforge.fab.research import list_methods, run_research_solve

_TESTS_DIR = Path(__file__).resolve().parents[1]
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


def test_list_methods_by_area():
    photo = list_methods("photolithography")
    assert any(m["id"] == "dedication_bind_spt" for m in photo)
    etch = list_methods("etch_timelink")
    assert any(m["id"].startswith("timelink") for m in etch)
    batch = list_methods("diffusion_furnace")
    assert any(m["id"] == "batch_construct" for m in batch)


def test_solve_photo_dedication():
    out = run_research_solve("fab_photo_dedication_v1", "dedication_bind_spt")
    assert out["domain"] == "fab"
    assert out["method_trace"]
    assert out["schedule"]["gantt_data"]
    assert "fab_evaluation" in out
    assert out["schedule"]["fab_hard_ok"] is True


def test_solve_timelink():
    out = run_research_solve("fab_etch_timelink_v1", "timelink_slack_spt")
    assert out["area"] == "etch_timelink"
    assert out["schedule"]["gantt_data"]


def test_solve_batch_construct():
    out = run_research_solve("fab_diffusion_batch_v1", "batch_construct")
    assert out["schedule"]["fab_batches"]
    assert out["schedule"]["fab_hard_ok"] is True


def test_method_area_mismatch():
    with pytest.raises(ValueError):
        run_research_solve("fab_photo_dedication_v1", "batch_construct")


def test_api_methods_and_solve(client):
    r = client.get("/api/fab/research/methods", params={"area": "photolithography"})
    assert r.status_code == 200
    assert r.json()["methods"]

    r2 = client.post(
        "/api/fab/research/solve",
        json={"scenario_id": "fab_photo_dedication_v1", "method": "dedication_bind_spt"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["schedule"]["fab_hard_ok"] is True
    assert len(body["method_trace"]) >= 4


def test_api_train_stub(client):
    r = client.post(
        "/api/fab/research/train",
        json={"scenario_id": "fab_photo_dedication_v1", "algo": "dqn", "epochs": 10},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "not_implemented"


def test_solve_with_model_override(client):
    loaded = client.post("/api/fab/scenarios/fab_photo_dedication_v1/load").json()
    jobs = loaded["jobs"]
    # bump first photo duration — still should run
    for t in jobs[0]["tasks"]:
        if t.get("process_area") == "photo":
            t["duration"] = int(t.get("duration") or 5) + 2
            break
    r = client.post(
        "/api/fab/research/solve",
        json={
            "scenario_id": "fab_photo_dedication_v1",
            "method": "dedication_bind_spt",
            "model": {
                "jobs": jobs,
                "machines": loaded["machines"],
                "strategy_defaults": loaded["strategy_defaults"],
                "fab_meta": loaded["fab_meta"],
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert any(t["step"] == "model_override" for t in body["method_trace"])
    assert body["schedule"]["fab_hard_ok"] is True
