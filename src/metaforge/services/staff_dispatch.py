"""人员排班：按甘特时刻 + 技能将员工直接派到运行中机台。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

MACHINE_SKILL = "数控"
STANDBY_SKILL = "辅助"


def _skills_of(staff: Dict[str, Any]) -> List[str]:
    raw = staff.get("skills") or []
    if isinstance(raw, str):
        return [raw]
    return [str(s) for s in raw if s]


def staff_can_operate(staff: Dict[str, Any], machine_id: int) -> bool:
    skills = _skills_of(staff)
    if MACHINE_SKILL in skills or "管理" in skills:
        return True
    role = str(staff.get("role") or "")
    if role in ("组长", "操作员") and STANDBY_SKILL not in skills:
        return True
    return False


def machines_running_at(
    gantt: List[Dict[str, Any]], sim_time: float
) -> List[Dict[str, Any]]:
    t = float(sim_time or 0)
    seen: Dict[int, Dict[str, Any]] = {}
    for task in gantt or []:
        mid = int(task.get("machine_id", -1))
        if mid < 0:
            continue
        start = float(task.get("start", 0))
        end = float(task.get("end", 0))
        if start <= t <= end:
            seen[mid] = {
                "machine_id": mid,
                "job_name": str(task.get("job_name") or ""),
                "job_id": task.get("job_id"),
            }
    return list(seen.values())


def _staff_sort_key(staff: Dict[str, Any]) -> Tuple[int, int]:
    skills = _skills_of(staff)
    role = str(staff.get("role") or "")
    level = str(staff.get("level") or "L1")
    level_rank = {"L1": 1, "L2": 2, "L3": 3}.get(level, 1)
    if role == "组长" or "管理" in skills:
        return (0, -level_rank)
    if MACHINE_SKILL in skills:
        return (1, -level_rank)
    return (2, -level_rank)


def assign_staff(
    gantt: List[Dict[str, Any]],
    staff_list: List[Dict[str, Any]],
    sim_time: float,
) -> List[Dict[str, Any]]:
    """将在岗且具备技能的员工派到当前运行中的机台；未派工员工不出现在结果中。"""
    running = machines_running_at(gantt, sim_time)
    active = [s for s in staff_list if s.get("is_active")]
    pool = sorted(active, key=_staff_sort_key)
    assignments: List[Dict[str, Any]] = []

    for machine in sorted(running, key=lambda m: int(m["machine_id"])):
        mid = int(machine["machine_id"])
        picked: Optional[Dict[str, Any]] = None
        for idx, s in enumerate(pool):
            if staff_can_operate(s, mid):
                picked = pool.pop(idx)
                break
        if picked:
            assignments.append(
                {
                    "staff_id": picked.get("id"),
                    "name": picked.get("name", ""),
                    "role": picked.get("role", ""),
                    "skills": _skills_of(picked),
                    "machine_id": mid,
                    "status": "working",
                    "job_name": machine.get("job_name", ""),
                }
            )
    return assignments


def _machine_by_id(db_machines: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    return {int(m["id"]): m for m in db_machines if m.get("id") is not None}


def position_for_machine(
    machine_id: int,
    db_machines: List[Dict[str, Any]],
) -> Tuple[float, float, float]:
    by_id = _machine_by_id(db_machines)
    m = by_id[int(machine_id)]
    mx = float(m.get("x", 0))
    mz = float(m.get("z", 0))
    side_z = 16 if mz < 0 else -16
    return mx - 10, 1.6, mz + side_z


def build_staff_dispatch_preview(
    gantt: List[Dict[str, Any]],
    staff_list: List[Dict[str, Any]],
    db_machines: List[Dict[str, Any]],
    sim_time: float,
) -> Dict[str, Any]:
    assignments = assign_staff(gantt, staff_list, sim_time)
    running = machines_running_at(gantt, sim_time)
    running_count = len(running)
    assigned_ids = {int(a["machine_id"]) for a in assignments}
    unassigned_machines = [
        int(m["machine_id"]) for m in running if int(m["machine_id"]) not in assigned_ids
    ]

    placed: List[Dict[str, Any]] = []
    for a in assignments:
        x, y, z = position_for_machine(int(a["machine_id"]), db_machines)
        placed.append(
            {
                **a,
                "id": a["staff_id"],
                "x": round(x, 2),
                "y": y,
                "z": round(z, 2),
            }
        )

    skilled_active = sum(
        1 for s in staff_list if s.get("is_active") and staff_can_operate(s, 0)
    )

    return {
        "sim_time": round(float(sim_time or 0), 2),
        "assignments": placed,
        "unassigned_machines": unassigned_machines,
        "stats": {
            "running_machines": running_count,
            "assigned": len(placed),
            "skilled_active": skilled_active,
            "shortage": max(0, running_count - len(placed)),
        },
    }


def build_staff_snapshot(
    staff_list: List[Dict[str, Any]],
    db_machines: List[Dict[str, Any]],
    gantt: Optional[List[Dict[str, Any]]] = None,
    sim_time: float = 0,
) -> List[Dict[str, Any]]:
    """数字孪生用：仅展示当前时刻已派到机台的员工。"""
    if not gantt:
        return []
    preview = build_staff_dispatch_preview(gantt, staff_list, db_machines, sim_time)
    return preview["assignments"]
