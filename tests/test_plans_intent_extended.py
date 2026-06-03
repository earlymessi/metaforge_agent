"""计划意图扩展（复制/重命名/状态）。"""

from metaforge.plans.intent import parse_plan_intent


def test_parse_duplicate():
    p = parse_plan_intent("复制计划试产01为试产02")
    assert p["action"] == "duplicate"
    assert p["query"] == "试产01"
    assert p["new_name"] == "试产02"


def test_parse_rename():
    p = parse_plan_intent("重命名计划A为计划B")
    assert p["action"] == "rename"
    assert p["new_name"] == "计划B"


def test_parse_update_status():
    p = parse_plan_intent("标记计划A为已完成")
    assert p["action"] == "update_status"
    assert p["status"] == "done"


def test_parse_view_plan_by_name():
    p = parse_plan_intent("查看计划sss")
    assert p["action"] == "view"
    assert p["query"] == "sss"
    assert p["navigate_aps"] is True


def test_parse_view_plan_with_space():
    p = parse_plan_intent("查看计划 测试")
    assert p["action"] == "view"
    assert p["query"] == "测试"


def test_parse_view_all_plans_list():
    p = parse_plan_intent("查看所有计划")
    assert p["action"] == "list"


def test_view_not_matched_as_list():
    """「查看」含「查」字，不得误判为 list。"""
    p = parse_plan_intent("查看计划a")
    assert p is not None
    assert p["action"] != "list"
