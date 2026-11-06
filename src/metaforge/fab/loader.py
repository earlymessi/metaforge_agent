from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from metaforge.fab.models import FabScenarioPack
from metaforge.fab.schema import require_valid, validate_scenario_dict


def _repo_root() -> Path:
    # src/metaforge/fab/loader.py → parents[3] = repo root
    return Path(__file__).resolve().parents[3]


def scenarios_dir() -> Path:
    return _repo_root() / "data" / "fab_scenarios"


def list_scenario_files() -> List[Path]:
    root = scenarios_dir()
    if not root.is_dir():
        return []
    files = list(root.glob("*.yaml")) + list(root.glob("*.yml")) + list(root.glob("*.json"))
    return sorted(files, key=lambda p: p.name)


def list_scenario_ids() -> List[str]:
    ids: List[str] = []
    for path in list_scenario_files():
        try:
            pack = load_scenario_path(path)
            ids.append(pack.scenario_id)
        except Exception:
            # skip broken files in listing; load_scenario will raise
            ids.append(path.stem)
    return sorted(set(ids))


def list_scenario_summaries() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in list_scenario_files():
        pack = load_scenario_path(path)
        s = pack.summary()
        s["file"] = path.name
        out.append(s)
    out.sort(key=lambda x: x.get("scenario_id") or "")
    return out


def _read_raw(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        import json

        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: root must be a mapping")
    return data


def load_scenario_path(path: Path, *, validate: bool = True) -> FabScenarioPack:
    data = _read_raw(path)
    if validate:
        require_valid(data)
    return FabScenarioPack.from_dict(data)


def load_scenario(scenario_id: str, *, validate: bool = True) -> FabScenarioPack:
    sid = str(scenario_id).strip()
    if not sid:
        raise ValueError("scenario_id is empty")
    # prevent path traversal
    if "/" in sid or "\\" in sid or ".." in sid:
        raise ValueError("invalid scenario_id")

    matches = [p for p in list_scenario_files() if p.stem == sid]
    if not matches:
        # also allow match by scenario_id field inside file
        for path in list_scenario_files():
            try:
                raw = _read_raw(path)
            except Exception:
                continue
            if raw.get("scenario_id") == sid:
                matches.append(path)
                break
    if not matches:
        raise FileNotFoundError(f"FAB scenario not found: {sid}")
    return load_scenario_path(matches[0], validate=validate)


def try_validate_file(path: Path) -> tuple[bool, List[str]]:
    try:
        data = _read_raw(path)
    except Exception as exc:
        return False, [str(exc)]
    return validate_scenario_dict(data)
