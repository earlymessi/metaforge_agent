from metaforge.services.staff_dispatch import (
    assign_staff,
    build_staff_dispatch_preview,
    machines_running_at,
)


def _staff(sid, name, skills, role="操作员", active=True):
    return {
        "id": sid,
        "name": name,
        "role": role,
        "skills": skills,
        "shift": "早班",
        "is_active": active,
    }


def test_machines_running_at():
    gantt = [
        {"machine_id": 1, "start": 0, "end": 10, "job_name": "J1"},
        {"machine_id": 2, "start": 5, "end": 15, "job_name": "J2"},
    ]
    running = machines_running_at(gantt, 6)
    assert {m["machine_id"] for m in running} == {1, 2}


def test_assign_staff_with_shortage():
    gantt = [
        {"machine_id": 0, "start": 0, "end": 10, "job_name": "A"},
        {"machine_id": 1, "start": 0, "end": 10, "job_name": "B"},
        {"machine_id": 2, "start": 0, "end": 10, "job_name": "C"},
    ]
    staff = [
        _staff(1, "张三", ["数控"], "组长"),
        _staff(2, "李四", ["数控"]),
    ]
    preview = build_staff_dispatch_preview(
        gantt,
        staff,
        [{"id": 0, "x": 0, "z": -50}, {"id": 1, "x": 50, "z": -50}, {"id": 2, "x": 100, "z": -50}],
        5,
    )
    assert preview["stats"]["running_machines"] == 3
    assert preview["stats"]["assigned"] == 2
    assert preview["stats"]["shortage"] == 1
    assert len(preview["assignments"]) == 2
    assert preview["unassigned_machines"] == [2]
    assert all(a["status"] == "working" for a in preview["assignments"])
