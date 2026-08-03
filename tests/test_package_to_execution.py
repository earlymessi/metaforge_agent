import pytest

from metaforge.services.package_to_execution import extract_recommended_gantt, start_from_package


def test_extract_recommended_gantt_from_package():
    package = {
        "recommended_schedule_id": "edd",
        "evaluation": {
            "recommended_schedule_id": "edd",
            "candidates": [
                {"schedule_id": "edd", "solver": "edd", "gantt_data": [{"Job": "A", "Start": 0, "Finish": 2}]},
            ],
        },
    }
    solver_id, gantt = extract_recommended_gantt(package=package, candidates=None)
    assert solver_id == "edd"
    assert len(gantt) == 1


def test_extract_fails_without_recommendation():
    with pytest.raises(ValueError, match="recommended"):
        extract_recommended_gantt(package={"recommended_schedule_id": None}, candidates=[])


def test_extract_from_candidate_schedules_on_package():
    package = {
        "recommended_schedule_id": "spt",
        "candidate_schedules": [
            {"schedule_id": "spt", "solver": "spt", "gantt_data": [{"Job": "B", "Start": 0, "Finish": 3}]},
        ],
    }
    solver_id, gantt = extract_recommended_gantt(package=package)
    assert solver_id == "spt"
    assert gantt[0]["Job"] == "B"


def test_extract_with_explicit_candidates():
    package = {"recommended_schedule_id": "ga"}
    candidates = [
        {"schedule_id": "ga", "solver": "ga", "gantt_data": [{"Job": "C", "Start": 1, "Finish": 4}]},
    ]
    solver_id, gantt = extract_recommended_gantt(package=package, candidates=candidates)
    assert solver_id == "ga"
    assert len(gantt) == 1


class _FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class _FakeOrdersColl:
    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc):
        from bson import ObjectId

        oid = ObjectId()
        stored = {**doc, "_id": oid}
        self.docs[str(oid)] = stored
        return _FakeInsertResult(oid)

    async def update_one(self, filt, update):
        from bson import ObjectId

        oid = str(filt["_id"]) if not isinstance(filt["_id"], str) else filt["_id"]
        if isinstance(filt["_id"], ObjectId):
            oid = str(filt["_id"])
        doc = self.docs.get(oid)
        if not doc:
            return
        sets = update.get("$set") or {}
        doc.update(sets)

    async def find_one(self, filt):
        from bson import ObjectId

        oid = filt.get("_id")
        key = str(oid) if isinstance(oid, ObjectId) else str(oid)
        return self.docs.get(key)


class _FakeExecutionColl:
    def __init__(self):
        self.doc = None

    async def replace_one(self, filt, doc, upsert=False):
        self.doc = doc


def test_start_from_package_persist_and_start(monkeypatch):
    import asyncio

    gantt = [{"Job": "A", "Start": 0, "Finish": 2, "Machine": 0}]
    package = {"recommended_schedule_id": "edd"}
    candidates = [{"schedule_id": "edd", "solver": "edd", "gantt_data": gantt}]

    orders = _FakeOrdersColl()
    execution = _FakeExecutionColl()

    async def fake_start(execution_coll, orders_coll, *, plan_id, solver_id, sim_speed=60.0):
        order = await orders_coll.find_one({"_id": __import__("bson").ObjectId(plan_id)})
        assert order is not None
        assert "edd" in (order.get("schedule_result") or {})
        return {
            "status": "running",
            "plan_id": plan_id,
            "baseline_solver": solver_id,
            "baseline_gantt": gantt,
            "sim_speed": sim_speed,
        }

    monkeypatch.setattr(
        "metaforge.services.package_to_execution.start_execution",
        fake_start,
    )

    out = asyncio.run(
        start_from_package(
            execution,
            orders,
            package=package,
            candidates=candidates,
            jobs=[{"id": "A"}],
            persist_plan=True,
            sim_speed=30.0,
        )
    )
    assert out["baseline_gantt"]
    assert out["baseline_solver"] == "edd"
    assert len(orders.docs) == 1


def test_start_from_package_requires_plan_when_no_persist():
    import asyncio

    with pytest.raises(ValueError, match="plan_id"):
        asyncio.run(
            start_from_package(
                _FakeExecutionColl(),
                _FakeOrdersColl(),
                package={"recommended_schedule_id": "edd"},
                candidates=[
                    {"schedule_id": "edd", "solver": "edd", "gantt_data": [{"Job": "A", "Start": 0, "Finish": 1}]},
                ],
                persist_plan=False,
            )
        )


def test_start_from_package_no_recommendation():
    import asyncio

    with pytest.raises(ValueError, match="recommended"):
        asyncio.run(
            start_from_package(
                _FakeExecutionColl(),
                _FakeOrdersColl(),
                package={"recommended_schedule_id": None},
                candidates=[],
                persist_plan=True,
            )
        )


def test_start_from_package_ignores_missing_run_when_body_has_candidates(monkeypatch):
    import asyncio

    gantt = [{"Job": "A", "Start": 0, "Finish": 2}]
    orders = _FakeOrdersColl()

    async def fake_start(execution_coll, orders_coll, *, plan_id, solver_id, sim_speed=60.0):
        return {
            "status": "running",
            "plan_id": plan_id,
            "baseline_solver": solver_id,
            "baseline_gantt": gantt,
            "sim_speed": sim_speed,
        }

    monkeypatch.setattr(
        "metaforge.services.package_to_execution.start_execution",
        fake_start,
    )

    out = asyncio.run(
        start_from_package(
            _FakeExecutionColl(),
            orders,
            run_id="missing-run-id",
            package={"recommended_schedule_id": "edd"},
            candidates=[{"schedule_id": "edd", "solver": "edd", "gantt_data": gantt}],
            jobs=[{"id": "A"}],
            persist_plan=True,
        )
    )
    assert out["baseline_gantt"]
    assert out["baseline_solver"] == "edd"
