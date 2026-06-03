"""material Tool 测试。"""

from metaforge.tools.base import ToolContext
from metaforge.tools.load_all import load_all_tools
from metaforge.tools.registry import run_tool


def setup_module():
    load_all_tools()


def test_material_check_static():
    jobs = [
        {
            "name": "J1",
            "priority": 10,
            "bom": [{"material_id": "MAT_A", "quantity_per_unit": 10, "consume_mode": "job_start"}],
            "tasks": [{"machine_id": 0, "duration": 1}],
        }
    ]
    inventory = {"MAT_A": 5.0}
    ctx = ToolContext(custom_data=jobs)
    r = run_tool(
        "material.check_static",
        {"inventory": inventory, "material_names": {"MAT_A": "物料A"}},
        ctx,
    )
    assert r.ok, r.error
    assert r.data["feasible"] is False
    assert ctx.artifacts["material_check"]["feasible"] is False
