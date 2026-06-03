"""AGV 全局离线调度服务（两阶段：全局均衡分桶 + 局部路径排序）。"""

from __future__ import annotations

import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class DispatchConfig:
    """混合评分权重。"""

    w_balance: float = 0.5
    w_empty: float = 0.4
    w_order: float = 0.1
    travel_time_cost: float = 0.5


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _distance_between(
    src_mid: int,
    dst_mid: int,
    machine_pos: Dict[int, Tuple[float, float]],
    fallback_cost: float,
) -> float:
    if src_mid == -1:
        return fallback_cost
    if src_mid == dst_mid:
        return 0.0
    src = machine_pos.get(int(src_mid))
    dst = machine_pos.get(int(dst_mid))
    if not src or not dst:
        return fallback_cost
    return math.hypot(src[0] - dst[0], src[1] - dst[1]) / 100.0


def build_transfer_tasks(schedule_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从工序甘特提取跨机台搬运任务。"""
    jobs: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    now_ms = int(time.time() * 1000)

    for item in schedule_data:
        jid = item.get("job_id")
        if jid is None:
            continue
        jobs[jid].append(item)

    tasks: List[Dict[str, Any]] = []
    for jid, ops in jobs.items():
        ops.sort(key=lambda x: _to_float(x.get("start"), 0.0))
        for i in range(len(ops) - 1):
            curr_op = ops[i]
            next_op = ops[i + 1]
            from_mid = int(curr_op.get("machine_id", -1))
            to_mid = int(next_op.get("machine_id", -1))
            if from_mid == to_mid:
                continue
            pickup_time = _to_float(curr_op.get("end"), 0.0)
            deadline = _to_float(next_op.get("start"), pickup_time)
            tasks.append(
                {
                    "id": f"T-{jid}-{i}-{now_ms}",
                    "job_id": jid,
                    "job_name": curr_op.get("job_name", f"Job-{jid}"),
                    "from_machine": from_mid,
                    "to_machine": to_mid,
                    "pickup_time": pickup_time,
                    "delivery_deadline": deadline,
                    "gap": deadline - pickup_time,
                    "priority": "Normal",
                }
            )
    tasks.sort(key=lambda t: (_to_float(t.get("pickup_time")), int(t.get("from_machine", -1))))
    return tasks


def ensure_default_fleet(fleet_docs: Iterable[Dict[str, Any]], default_size: int = 4) -> List[Dict[str, Any]]:
    docs = [dict(x) for x in fleet_docs]
    if docs:
        return docs
    return [{"agv_id": i + 1, "location": -1, "status": "idle"} for i in range(default_size)]


def _assign_task_pools(
    tasks: List[Dict[str, Any]],
    fleet_state: Dict[int, Dict[str, float]],
    machine_pos: Dict[int, Tuple[float, float]],
    cfg: DispatchConfig,
) -> Dict[int, List[Dict[str, Any]]]:
    """阶段一：全局均衡分桶。"""
    pools: Dict[int, List[Dict[str, Any]]] = {agv_id: [] for agv_id in fleet_state.keys()}
    for task in tasks:
        if not pools:
            break
        avg = len(tasks) / max(1, len(pools))
        candidates = []
        for agv_id, st in fleet_state.items():
            load_after = len(pools[agv_id]) + 1
            load_penalty = max(0.0, load_after - avg)
            empty = _distance_between(
                int(st.get("location", -1)),
                int(task["from_machine"]),
                machine_pos,
                cfg.travel_time_cost,
            )
            order_penalty = max(0.0, _to_float(st.get("free_at"), 0.0) - _to_float(task.get("pickup_time"), 0.0))
            score = cfg.w_balance * load_penalty + cfg.w_empty * empty + cfg.w_order * order_penalty
            candidates.append((score, agv_id))
        candidates.sort(key=lambda x: x[0])
        pools[candidates[0][1]].append(task)
    return pools


def _sort_pool_by_local_route(
    tasks: List[Dict[str, Any]],
    start_loc: int,
    machine_pos: Dict[int, Tuple[float, float]],
    cfg: DispatchConfig,
) -> List[Dict[str, Any]]:
    """阶段二：池内按局部路径+时间排序。"""
    pending = list(tasks)
    ordered: List[Dict[str, Any]] = []
    cur = start_loc
    while pending:
        pending.sort(
            key=lambda t: (
                _distance_between(cur, int(t["from_machine"]), machine_pos, cfg.travel_time_cost),
                _to_float(t.get("pickup_time"), 0.0),
            )
        )
        nxt = pending.pop(0)
        ordered.append(nxt)
        cur = int(nxt["to_machine"])
    return ordered


def dispatch_agv_global(
    schedule_data: List[Dict[str, Any]],
    fleet_docs: List[Dict[str, Any]],
    *,
    machine_pos: Optional[Dict[int, Tuple[float, float]]] = None,
    cfg: Optional[DispatchConfig] = None,
) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, float]]]:
    """执行两阶段全局调度，返回任务与最终车队状态。"""
    cfg = cfg or DispatchConfig()
    machine_pos = machine_pos or {}
    tasks = build_transfer_tasks(schedule_data)
    fleet_docs = ensure_default_fleet(fleet_docs)
    fleet_state: Dict[int, Dict[str, float]] = {
        int(doc["agv_id"]): {
            "location": float(doc.get("location", -1)),
            "free_at": 0.0,
        }
        for doc in fleet_docs
    }
    if not tasks or not fleet_state:
        return [], fleet_state

    pools = _assign_task_pools(tasks, fleet_state, machine_pos, cfg)
    out: List[Dict[str, Any]] = []
    for agv_id, pool in pools.items():
        ordered_pool = _sort_pool_by_local_route(pool, int(fleet_state[agv_id]["location"]), machine_pos, cfg)
        rank = 0
        for task in ordered_pool:
            rank += 1
            empty = _distance_between(
                int(fleet_state[agv_id]["location"]),
                int(task["from_machine"]),
                machine_pos,
                cfg.travel_time_cost,
            )
            arrival = max(fleet_state[agv_id]["free_at"] + empty, _to_float(task["pickup_time"], 0.0))
            finish = arrival + cfg.travel_time_cost
            lateness = max(0.0, finish - _to_float(task["delivery_deadline"], finish))
            usage = rank
            score_breakdown = {
                "load_penalty": max(0.0, usage - (len(tasks) / max(1, len(pools)))),
                "empty_cost": empty,
                "order_penalty": lateness,
            }
            score = (
                cfg.w_balance * score_breakdown["load_penalty"]
                + cfg.w_empty * score_breakdown["empty_cost"]
                + cfg.w_order * score_breakdown["order_penalty"]
            )
            dispatched = dict(task)
            dispatched.update(
                {
                    "assigned_agv": agv_id,
                    "dispatch_rank": rank,
                    "route": [int(task["from_machine"]), int(task["to_machine"])],
                    "arrival_time": round(arrival, 4),
                    "finish_time": round(finish, 4),
                    "is_seamless": empty == 0.0,
                    "priority": "High" if lateness > 0 else "Normal",
                    "score": round(score, 6),
                    "score_breakdown": score_breakdown,
                }
            )
            out.append(dispatched)
            fleet_state[agv_id]["location"] = float(task["to_machine"])
            fleet_state[agv_id]["free_at"] = float(finish)
    out.sort(key=lambda t: (_to_float(t.get("pickup_time"), 0.0), int(t.get("assigned_agv", 0))))
    return out, fleet_state


async def persist_dispatch_result(
    *,
    agv_tasks_collection,
    agv_fleet_collection,
    dispatched_tasks: List[Dict[str, Any]],
    fleet_state: Dict[int, Dict[str, float]],
) -> Dict[str, Any]:
    """写入任务与车队状态。"""
    batch_id = uuid.uuid4().hex[:12]
    now = datetime.now()
    if dispatched_tasks:
        docs = []
        for task in dispatched_tasks:
            docs.append(
                {
                    "batch_id": batch_id,
                    "task_id": task["id"],
                    "job_name": task.get("job_name", ""),
                    "from_machine": task.get("from_machine"),
                    "to_machine": task.get("to_machine"),
                    "assigned_agv": task.get("assigned_agv"),
                    "pickup_time": task.get("pickup_time"),
                    "delivery_deadline": task.get("delivery_deadline"),
                    "dispatch_rank": task.get("dispatch_rank"),
                    "route": task.get("route", []),
                    "score": task.get("score"),
                    "score_breakdown": task.get("score_breakdown", {}),
                    "is_seamless": task.get("is_seamless", False),
                    "dispatched": False,
                    "dispatch_status": "pending",
                    "created_at": now,
                }
            )
        await agv_tasks_collection.insert_many(docs)

    for agv_id, st in fleet_state.items():
        await agv_fleet_collection.update_one(
            {"agv_id": int(agv_id)},
            {
                "$set": {
                    "location": int(st.get("location", -1)),
                    "status": "idle",
                    "last_updated": now,
                }
            },
            upsert=True,
        )
    final_fleet_status = [
        {
            "id": int(agv_id),
            "location": int(st.get("location", -1)),
            "free_at": float(st.get("free_at", 0.0)),
        }
        for agv_id, st in sorted(fleet_state.items(), key=lambda x: x[0])
    ]
    return {"batch_id": batch_id, "fleet_status": final_fleet_status}
