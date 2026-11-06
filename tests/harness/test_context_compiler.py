from metaforge.harness.context import compile_planning_context


def test_context_hash_stable_for_same_input():
    kwargs = dict(
        user_goal="保证交期",
        jobs=[{"job_id": "A", "due_date": 5, "priority": 2}],
        machines=[{"machine_id": "M1"}],
    )
    a = compile_planning_context(**kwargs)
    b = compile_planning_context(**kwargs)
    assert a.context_hash == b.context_hash
    assert len(a.context_hash) == 16
    assert a.user_goal == "保证交期"
    assert a.orders_summary[0]["job_id"] == "A"


def test_context_hash_changes_when_goal_changes():
    jobs = [{"job_id": "A"}]
    a = compile_planning_context(user_goal="交期优先", jobs=jobs)
    b = compile_planning_context(user_goal="能耗优先", jobs=jobs)
    assert a.context_hash != b.context_hash
