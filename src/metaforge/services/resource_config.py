"""能耗/资源默认配置（与 tests/main.py 初始化口径一致）。"""

from __future__ import annotations

import copy
from typing import Any, Dict

DEFAULT_RESOURCE_CONFIG: Dict[str, Any] = {
    "_id": "global_config",
    "machine_powers": {
        "0": 12.0,
        "1": 5.5,
        "2": 8.0,
        "3": 3.0,
        "4": 15.0,
        "5": 4.0,
        "6": 2.5,
        "7": 1.0,
        "8": 6.0,
        "9": 4.5,
    },
    "hourly_prices": (
        [0.3] * 8
        + [1.2] * 4
        + [0.8] * 3
        + [1.2] * 4
        + [0.8] * 5
    ),
    "maintenance_limits": {
        "0": 10.0,
        "1": 12.0,
        "2": 8.0,
        "3": 15.0,
        "4": 6.0,
        "5": 10.0,
        "6": 10.0,
        "7": 20.0,
        "8": 10.0,
        "9": 10.0,
    },
    "downtime_blocks": [],
}


def default_resource_config() -> Dict[str, Any]:
    """返回可修改的默认能耗配置副本。"""
    return copy.deepcopy(DEFAULT_RESOURCE_CONFIG)


def effective_resource_config(resource_config: Any) -> Dict[str, Any]:
    """合并调用方配置与默认机台功率/电价（缺字段时补齐）。"""
    base = default_resource_config()
    if not resource_config or not isinstance(resource_config, dict):
        return base
    out = {**base, **resource_config}
    if not out.get("machine_powers"):
        out["machine_powers"] = base["machine_powers"]
    if not out.get("hourly_prices"):
        out["hourly_prices"] = base["hourly_prices"]
    return out
