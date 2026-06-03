"""compare Tool 测试。"""

from metaforge.agent.scheduling_agent import STRATEGY_TEMPLATES
from metaforge.tools.base import ToolContext
from metaforge.tools.load_all import load_all_tools
from metaforge.tools.registry import run_tool


def setup_module():
    load_all_tools()


def _jobs():
    return [
        {
            "name": "工单A",
            "priority": 10,
            "due_date": 20.0,
            "tasks": [
                {"machine_id": 0, "duration": 3},
                {"machine_id": 1, "duration": 2},
            ],
        },
        {
            "name": "工单B",
            "priority": 20,
            "due_date": 25.0,
            "tasks": [
                {"machine_id": 1, "duration": 4},
                {"machine_id": 0, "duration": 2},
            ],
        },
    ]


def test_compare_variants_two_strategies():
    variants = []
    for tpl in STRATEGY_TEMPLATES[:2]:
        variants.append(
            {
                "variant_id": tpl["id"],
                "label": tpl["name"],
                "scheduling": {
                    "solvers": ["spt"],
                    "weights": tpl["weights"],
                },
            }
        )
    ctx = ToolContext(custom_data=_jobs())
    r = run_tool("compare.variants", {"variants": variants, "recommend_metric": "best_score"}, ctx)
    assert r.ok, r.error
    assert r.data.get("recommendation")
    assert len(r.data.get("variants", [])) == 2
    assert ctx.artifacts.get("what_if")
