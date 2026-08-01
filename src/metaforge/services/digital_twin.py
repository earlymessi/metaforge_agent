"""数字孪生快照：机台 / AGV / 人员与甘特仿真时刻对齐。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from metaforge.services.staff_dispatch import build_staff_snapshot as _build_staff_snapshot


def build_machines_snapshot(
    db_machines: List[Dict[str, Any]],
    gantt: List[Dict[str, Any]],
    current_sim_time: float,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    t = float(current_sim_time or 0)
    for m in db_machines:
        mid = int(m["id"])
        status = "idle"
        current_job = ""
        for task in gantt or []:
            if int(task.get("machine_id", -1)) != mid:
                continue
            if float(task.get("start", 0)) <= t <= float(task.get("end", 0)):
                status = "running"
                current_job = str(task.get("job_name") or "")
                break
        out.append(
            {
                "id": mid,
                "x": float(m.get("x", 0)),
                "y": float(m.get("y", 7.5)),
                "z": float(m.get("z", 0)),
                "status": status,
                "current_job": current_job,
            }
        )
    return out


async def build_agv_snapshot(
    agv_fleet_collection,
    db_machines: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    agvs = await agv_fleet_collection.find().to_list(100)
    by_id = {int(m["id"]): m for m in db_machines if m.get("id") is not None}
    agv_data: List[Dict[str, Any]] = []
    for agv in agvs:
        sx, sz = 0.0, 0.0
        loc = agv.get("location", -1)
        if loc != -1 and int(loc) in by_id:
            target_m = by_id[int(loc)]
            sx = float(target_m["x"])
            sz = float(target_m["z"]) + (15 if float(target_m["z"]) < 0 else -15)
        agv_data.append(
            {
                "id": agv.get("agv_id"),
                "x": sx,
                "y": 1.0,
                "z": sz,
                "status": agv.get("status", "idle"),
            }
        )
    return agv_data


async def build_staff_snapshot(
    staff_collection,
    db_machines: List[Dict[str, Any]],
    gantt: Optional[List[Dict[str, Any]]] = None,
    sim_time: float = 0,
) -> List[Dict[str, Any]]:
    staff_list = await staff_collection.find().to_list(100)
    return _build_staff_snapshot(staff_list, db_machines, gantt=gantt, sim_time=sim_time)
