from fastapi.testclient import TestClient

from metaforge.scenario.store import ScenarioStore


def test_scenarios_crud_and_run_mock(monkeypatch):
    store = ScenarioStore()
    import metaforge.scenario.store as store_mod

    monkeypatch.setattr(store_mod, "default_store", store)

    from main import app
    import main as main_mod

    client = TestClient(app)

    created = client.post(
        "/api/scenarios",
        json={
            "name": "fault-then-due",
            "steps": [
                {"event_type": "machine_breakdown", "params": {"machine_id": 0}},
                {"event_type": "due_date_change", "params": {"due_date_changes": []}},
            ],
        },
    )
    assert created.status_code == 200, created.text
    sid = created.json()["id"]

    listed = client.get("/api/scenarios")
    assert listed.status_code == 200
    assert any(i["id"] == sid for i in listed.json()["items"])

    got = client.get(f"/api/scenarios/{sid}")
    assert got.status_code == 200
    assert got.json()["name"] == "fault-then-due"

    updated = client.put(
        f"/api/scenarios/{sid}",
        json={
            "name": "fault-only",
            "steps": [{"event_type": "machine_breakdown", "params": {"machine_id": 1}}],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "fault-only"

    presets = client.get("/api/scenarios/presets")
    assert presets.status_code == 200
    assert len(presets.json()["items"]) >= 3

    async def fake_dispatch(envelope):
        if envelope.get("event_type") == "machine_breakdown":
            raise RuntimeError("boom")
        return {"ok": True, "impact_report": {}}

    monkeypatch.setattr(main_mod, "_event_dispatch_from_request", fake_dispatch)

    async def fake_get_state(_coll):
        return {
            "status": "running",
            "jobs_snapshot": [{"name": "J1"}],
            "baseline_gantt": [{"Job": "J1", "Start": 0, "Finish": 1}],
            "baseline_solver": "edd",
            "sim_time": 0,
        }

    async def fake_tick(_coll, doc):
        return doc

    monkeypatch.setattr(
        "metaforge.services.production_execution.get_state",
        fake_get_state,
    )
    monkeypatch.setattr(
        "metaforge.services.production_execution.tick_sim_time",
        fake_tick,
    )

    ran = client.post(f"/api/scenarios/{sid}/run", json={})
    assert ran.status_code == 200, ran.text
    body = ran.json()
    assert body["status"] == "failed"
    assert len(body["timeline"]) == 1
    assert body["timeline"][0]["status"] == "failed"

    deleted = client.delete(f"/api/scenarios/{sid}")
    assert deleted.status_code == 200
    assert client.get(f"/api/scenarios/{sid}").status_code == 404
