"""BOM / 物料约束单元测试。"""

from metaforge.utils.material_constraints import (
    check_jobs_material_static,
    job_bom_demand,
    simulate_schedule_materials,
)


class _Job:
    def __init__(self, name, bom=None, quantity=1, priority=10, tasks=None):
        self.name = name
        self.bom = bom or []
        self.quantity = quantity
        self.priority = priority
        self.tasks = tasks or []


def test_job_bom_demand_with_quantity():
    job = _Job(
        "A",
        quantity=10,
        bom=[{"material_id": "MAT_STEEL", "quantity_per_unit": 2.0, "consume_mode": "job_start"}],
    )
    assert job_bom_demand(job)["MAT_STEEL"] == 20.0


def test_static_check_shortage():
    jobs = [
        _Job("J1", bom=[{"material_id": "MAT_STEEL", "quantity_per_unit": 100, "consume_mode": "job_start"}]),
    ]
    inv = {"MAT_STEEL": 50.0}
    report = check_jobs_material_static(jobs, inv)
    assert report["feasible"] is False
    assert report["summary"][0]["shortage"] == 50.0


def test_simulate_job_start_deduct_at_first_op():
    jobs = [
        _Job(
            "J1",
            bom=[{"material_id": "MAT_STEEL", "quantity_per_unit": 30, "consume_mode": "job_start"}],
        ),
    ]
    schedule = [
        {"job_id": 0, "machine_id": 0, "start": 5, "end": 10, "operation_id": 0},
    ]
    sim = simulate_schedule_materials(
        schedule,
        jobs,
        {"MAT_STEEL": 100.0},
        safe_levels={"MAT_STEEL": 0},
    )
    assert sim["timeline"][5]["MAT_STEEL"] == 70.0
    assert sim["feasible"] is True
    assert sim["safe_warnings"] == []


def test_simulate_safe_warning_vs_shortage():
    jobs = [
        _Job(
            "J1",
            bom=[{"material_id": "MAT_STEEL", "quantity_per_unit": 5, "consume_mode": "per_hour"}],
        ),
    ]
    schedule = [
        {"job_id": 0, "machine_id": 0, "start": 0, "end": 10, "operation_id": 0},
    ]
    sim = simulate_schedule_materials(
        schedule,
        jobs,
        {"MAT_STEEL": 120.0},
        safe_levels={"MAT_STEEL": 100.0},
    )
    assert sim["feasible"] is True
    assert sim["has_safe_warning"] is True
    assert len(sim["shortages"]) == 0
    assert len(sim["safe_warnings"]) >= 1
    assert all(w["left"] >= 0 for w in sim["safe_warnings"])
    assert all(w["event_type"] == "safe_warning" for w in sim["safe_warnings"])

    sim2 = simulate_schedule_materials(
        schedule,
        jobs,
        {"MAT_STEEL": 20.0},
        safe_levels={"MAT_STEEL": 100.0},
    )
    assert sim2["feasible"] is False
    assert len(sim2["shortages"]) >= 1
    assert all(s["left"] < 0 for s in sim2["shortages"])
