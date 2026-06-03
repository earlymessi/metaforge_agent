"""核心 API 冒烟测试（无需启动服务，直接调用 FastAPI 路由函数）。"""

from metaforge.problems.jobshop import Job, JobShopProblem, Task
from metaforge.utils.compare_solvers import compare_solvers
from metaforge.utils.metrics import compute_bottleneck_report


def test_compare_solvers_with_seed_and_bottleneck():
    jobs = [
        Job(
            tasks=[
                Task(machine_id=0, duration=3, id=0),
                Task(machine_id=1, duration=2, id=1),
            ],
            id=0,
            priority=10,
            due_date=8.0,
        ),
        Job(
            tasks=[
                Task(machine_id=1, duration=4, id=0),
                Task(machine_id=0, duration=2, id=1),
            ],
            id=1,
            priority=50,
            due_date=10.0,
        ),
    ]
    problem = JobShopProblem(jobs, instance_name="smoke")
    results = compare_solvers(
        ["spt", "ts"],
        problem,
        weights={"makespan": 1.0, "weighted_tardiness_total": 0.5, "energy_cost": 0.0, "machine_busy_cv": 5.0},
        random_seed=42,
    )
    assert "spt" in results
    assert results["spt"].get("gantt_data")
    assert "bottleneck_report" in results["spt"]
    assert results["spt"]["bottleneck_report"].get("machines")
    assert results["spt"].get("optimization_mode") == "rule_construct"
    assert results["spt"].get("family") == "rule"


def test_resolve_duration_logic():
    from main import TaskData, _resolve_task_duration

    t = TaskData(duration=1, setup_time=2.0, unit_time=3.0, quantity=4)
    assert _resolve_task_duration(t) == 14


def test_tools_registry_lists_scheduling_tools():
    from metaforge.tools.load_all import load_all_tools
    from metaforge.tools.registry import list_tools

    load_all_tools()
    names = {t["name"] for t in list_tools()}
    assert "scheduling.parse_intent" in names
    assert "scheduling.run" in names
    assert "material.check_static" in names
    assert "delivery.assess" in names


def test_async_run_routes_registered():
    from main import app

    route_paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/run/async" in route_paths
    assert "/api/run/status/{task_id}" in route_paths
    assert "/api/run/result/{task_id}" in route_paths
    assert "/api/materials/check_jobs" in route_paths
    assert "/api/tools/registry" in route_paths
    assert "/api/solvers/catalog" in route_paths
    assert "/api/objectives/schema" in route_paths
    assert "/api/solvers/{solver_id}/run" in route_paths


def test_solver_registry_catalog_and_aliases():
    from metaforge.utils.solver_registry import get_solver_catalog, resolve_solver_id

    catalog = get_solver_catalog()
    assert catalog["total"] >= 14
    ids = {s["id"] for s in catalog["solvers"]}
    assert "ppo" in ids
    assert "ts" in ids
    assert resolve_solver_id("PPO") == "ppo"
    assert resolve_solver_id("ts") == "ts"

    ts = next(s for s in catalog["solvers"] if s["id"] == "ts")
    assert ts["supports_weights_in_search"] is True
    assert ts["optimization_mode"] == "multiobjective_search"


def test_objectives_schema():
    from metaforge.utils.objectives import get_objectives_schema

    schema = get_objectives_schema()
    assert "objectives" in schema
    assert "default_weights" in schema


def test_run_single_solver():
    from metaforge.utils.compare_solvers import run_single_solver

    jobs = [
        Job(
            tasks=[
                Task(machine_id=0, duration=3, id=0),
                Task(machine_id=1, duration=2, id=1),
            ],
            id=0,
            priority=10,
            due_date=8.0,
        ),
    ]
    problem = JobShopProblem(jobs, instance_name="single")
    sr = run_single_solver(
        "spt",
        problem,
        weights={"makespan": 1.0, "weighted_tardiness_total": 0.5, "energy_cost": 0.0, "machine_busy_cv": 5.0},
        random_seed=42,
    )
    assert sr.solver_id == "spt"
    d = sr.to_api_dict()
    assert d["best_score"] > 0
    assert d["optimization_mode"] == "rule_construct"


def test_machine_downtime_blocks_delay_schedule():
    from metaforge.problems.jobshop import Job, JobShopProblem, Task

    jobs = [
        Job(
            tasks=[Task(machine_id=0, duration=5, id=0)],
            id=0,
            priority=10,
        )
    ]
    problem = JobShopProblem(jobs)
    problem.machines[0].maintenance.append({"start": 0.0, "end": 8.0})

    schedule = problem.get_schedule([0])
    assert schedule[0]["start"] >= 8.0
    assert schedule[0]["end"] == 13.0


def test_multi_agent_routes_registered():
    from main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/orchestrator/run" in paths
    assert "/api/orchestrator/session/{session_id}" in paths
    assert "/api/agents/registry" in paths
    assert "/api/agents/scheduling/run" in paths
    assert "/api/agents/commitment/run" in paths
    assert "/api/agents/kitting/run" in paths
    assert "/api/agents/events/run" in paths
    assert "/api/agents/whatif/run" in paths
    assert "/api/agents/pipeline/run" in paths
    assert "/api/db/propose_save" in paths
    assert "/api/db/confirm_save" in paths
    assert "/api/llm/status" in paths
    assert "/api/mcp/status" in paths
    assert "/api/orchestrator/preview" in paths


def test_tools_registry_lists_phase2_tools():
    from metaforge.tools.load_all import load_all_tools
    from metaforge.tools.registry import list_tools

    load_all_tools()
    names = {t["name"] for t in list_tools()}
    assert "events.parse_event" in names
    assert "events.reschedule" in names
    assert "kitting.build_report" in names
    assert "compare.variants" in names
    assert "data.load_plan" in names
    assert "data.propose_persist" in names


def test_agents_registry_has_six():
    from metaforge.agents.registry_meta import list_agents

    agents = list_agents()
    assert len(agents) == 6
    assert {a["id"] for a in agents} == {
        "scheduling",
        "events",
        "kitting",
        "commitment",
        "whatif",
        "plans",
    }
    implemented = {a["id"] for a in agents if a.get("implemented")}
    assert implemented == {
        "scheduling",
        "events",
        "kitting",
        "commitment",
        "whatif",
        "plans",
    }
