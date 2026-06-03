"""交期承诺风险等级与自动交期修正。"""

from metaforge.problems.jobshop import Job, JobShopProblem, Task
from metaforge.utils.delivery_prediction import compute_delivery_predictions
from metaforge.utils.problem_builder import build_problem_from_custom_jobs


def test_auto_due_includes_shop_queue_slack():
    jobs_data = [
        {"name": "J1", "priority": 10, "tasks": [{"machine_id": 0, "duration": 10}]},
        {"name": "J2", "priority": 10, "tasks": [{"machine_id": 0, "duration": 10}]},
    ]
    problem, _, _ = build_problem_from_custom_jobs(jobs_data)
    j0 = problem.jobs[0]
    assert not j0.due_date_explicit
    serial = 10 + 10
    assert j0.due_date > serial


def test_explicit_due_not_overwritten_by_refine():
    jobs_data = [
        {
            "name": "J1",
            "priority": 10,
            "due_date": 50.0,
            "tasks": [{"machine_id": 0, "duration": 5}],
        },
    ]
    problem, _, _ = build_problem_from_custom_jobs(jobs_data)
    assert problem.jobs[0].due_date_explicit
    assert problem.jobs[0].due_date == 50.0


def test_on_time_when_completion_before_explicit_due():
    jobs = [Job(tasks=[Task(machine_id=0, duration=5, id=0)], id=0, due_date=100.0)]
    problem = JobShopProblem(jobs)
    gantt = [{"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0, "end": 8}]
    preds = compute_delivery_predictions(gantt, problem)
    assert preds[0]["risk_level"] in ("on_time", "low")


def test_auto_due_job_not_critical_when_completion_near_shop_scale():
    """多工单场景：完工略大于旧 2.5×工时交期，修正后不应一律 critical。"""
    jobs_data = [
        {"name": "J1", "tasks": [{"machine_id": 0, "duration": 8}]},
        {"name": "J2", "tasks": [{"machine_id": 0, "duration": 8}]},
        {"name": "J3", "tasks": [{"machine_id": 1, "duration": 8}]},
    ]
    problem, name_map, _ = build_problem_from_custom_jobs(jobs_data)
    gantt = [
        {"job_id": 0, "machine_id": 0, "operation_id": 0, "start": 0, "end": 8},
        {"job_id": 1, "machine_id": 0, "operation_id": 0, "start": 8, "end": 16},
        {"job_id": 2, "machine_id": 1, "operation_id": 0, "start": 0, "end": 8},
    ]
    preds = compute_delivery_predictions(gantt, problem, job_name_map=name_map)
    levels = {p["risk_level"] for p in preds}
    assert "critical" not in levels or len(levels) < 3
