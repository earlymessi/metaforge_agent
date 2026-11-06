"""Map FabScenarioPack → planning jobs + strategy defaults (domain=fab)."""

from __future__ import annotations

from typing import Any, Dict, List

from metaforge.fab.models import FabScenarioPack


def _collect_machine_ids(pack: FabScenarioPack) -> List[str]:
    seen: List[str] = []
    entities = pack.entities or {}

    def _add(mid: str) -> None:
        if mid and mid not in seen:
            seen.append(mid)

    for m in entities.get("machines") or []:
        if isinstance(m, dict):
            _add(str(m.get("id") or ""))

    for lot in entities.get("lots") or []:
        if not isinstance(lot, dict):
            continue
        for op in lot.get("ops") or []:
            if not isinstance(op, dict):
                continue
            if op.get("machine_id") is not None:
                _add(str(op["machine_id"]))
            for opt in op.get("machine_options") or []:
                _add(str(opt))

    return seen


def _build_machine_id_map(pack: FabScenarioPack) -> Dict[str, int]:
    ids = _collect_machine_ids(pack)
    return {mid: i for i, mid in enumerate(ids)}


def _map_mid(mid: str, machine_id_map: Dict[str, int]) -> int:
    key = str(mid)
    if key not in machine_id_map:
        raise ValueError(f"unknown machine id in scenario: {key!r}")
    return machine_id_map[key]


def _lot_to_job(lot: Dict[str, Any], machine_id_map: Dict[str, int]) -> Dict[str, Any]:
    lot_id = str(lot.get("id") or "")
    job: Dict[str, Any] = {
        "name": lot_id,
        "job_id": lot_id,
        "priority": 10,
        "tasks": [],
    }
    if lot.get("family_id") is not None:
        job["family_id"] = lot["family_id"]
    release = lot.get("release")
    if release is not None:
        job["material_arrival"] = float(release)

    tasks: List[Dict[str, Any]] = []
    for op in lot.get("ops") or []:
        if not isinstance(op, dict):
            continue
        task: Dict[str, Any] = {
            "name": str(op.get("id") or ""),
            "duration": max(1, int(round(float(op.get("duration") or 1)))),
        }
        if op.get("process_area") is not None:
            task["process_area"] = op["process_area"]
        if op.get("layer_index") is not None:
            task["layer_index"] = op["layer_index"]
        if op.get("is_dedication_mark") is not None:
            task["is_dedication_mark"] = bool(op["is_dedication_mark"])

        if op.get("machine_id") is not None:
            task["machine_id"] = _map_mid(str(op["machine_id"]), machine_id_map)
        opts = op.get("machine_options")
        if opts:
            task["machine_options"] = [_map_mid(str(o), machine_id_map) for o in opts]
        tasks.append(task)

    job["tasks"] = tasks
    return job


def _extract_timelinks(pack: FabScenarioPack) -> List[Dict[str, Any]]:
    links: List[Dict[str, Any]] = []
    seen: set[tuple] = set()

    def _add(entry: Dict[str, Any]) -> None:
        key = (
            entry.get("from_op"),
            entry.get("to_op"),
            entry.get("max_lag"),
        )
        if key in seen:
            return
        seen.add(key)
        links.append(entry)

    for tl in (pack.raw or {}).get("timelinks_hard") or []:
        if isinstance(tl, dict):
            _add(dict(tl))

    for c in pack.constraints_hard:
        if c.get("type") != "max_lag_between_ops":
            continue
        entry = {k: v for k, v in c.items() if k != "type"}
        if entry:
            _add(entry)

    return links


def _batch_machines(pack: FabScenarioPack, machine_id_map: Dict[str, int]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in (pack.entities or {}).get("machines") or []:
        if not isinstance(m, dict):
            continue
        mtype = str(m.get("type") or "")
        if mtype != "batch_furnace" and m.get("max_batch_size") is None:
            continue
        mid = str(m.get("id") or "")
        entry: Dict[str, Any] = {
            "id": mid,
            "machine_index": machine_id_map.get(mid),
            "type": mtype,
        }
        if m.get("max_batch_size") is not None:
            entry["max_batch_size"] = m["max_batch_size"]
        out.append(entry)
    return out


def _machines_list(pack: FabScenarioPack, machine_id_map: Dict[str, int]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in (pack.entities or {}).get("machines") or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "")
        entry: Dict[str, Any] = {"id": mid, "machine_index": machine_id_map.get(mid)}
        for k, v in m.items():
            if k != "id":
                entry[k] = v
        out.append(entry)
    return out


def _strategy_defaults(pack: FabScenarioPack) -> Dict[str, Any]:
    return {
        "hard_constraints": [dict(c) for c in pack.constraints_hard],
        "soft_constraints": [dict(c) for c in pack.constraints_soft],
        "objectives": dict(pack.objectives_default or {}),
    }


def pack_to_planning(pack: FabScenarioPack) -> Dict[str, Any]:
    machine_id_map = _build_machine_id_map(pack)
    lots = (pack.entities or {}).get("lots") or []
    jobs = [_lot_to_job(lot, machine_id_map) for lot in lots if isinstance(lot, dict)]

    return {
        "domain": "fab",
        "scenario_id": pack.scenario_id,
        "jobs": jobs,
        "machines": _machines_list(pack, machine_id_map),
        "strategy_defaults": _strategy_defaults(pack),
        "fab_meta": {
            "area": pack.area,
            "physics_refs": list(pack.physics_refs),
            "out_of_scope": list(pack.out_of_scope),
            "timelinks": _extract_timelinks(pack),
            "batch_machines": _batch_machines(pack, machine_id_map),
            "machine_id_map": machine_id_map,
        },
    }
