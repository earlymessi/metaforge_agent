"""物料主数据（materials_inventory 集合）默认种子与自愈。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

DEFAULT_MATERIALS: List[Dict[str, Any]] = [
    {
        "id": "MAT_STEEL",
        "name": "标准钢材",
        "current_stock": 500.0,
        "safe_level": 100.0,
        "unit": "kg",
    },
    {
        "id": "MAT_ALUM",
        "name": "铝合金板",
        "current_stock": 300.0,
        "safe_level": 50.0,
        "unit": "kg",
    },
    {
        "id": "MAT_PLASTIC",
        "name": "工业塑料",
        "current_stock": 200.0,
        "safe_level": 80.0,
        "unit": "kg",
    },
    {
        "id": "MAT_SCREW",
        "name": "高强螺栓",
        "current_stock": 1000.0,
        "safe_level": 200.0,
        "unit": "pcs",
    },
]


async def ensure_default_materials(collection) -> int:
    """集合为空时写入默认物料（不覆盖已有记录）。"""
    count = await collection.count_documents({})
    if count == 0:
        await collection.insert_many(deepcopy(DEFAULT_MATERIALS))
        return len(DEFAULT_MATERIALS)
    return count


async def fetch_materials_catalog(collection, *, ensure: bool = True) -> List[Dict[str, Any]]:
    if ensure:
        await ensure_default_materials(collection)
    materials = await collection.find().to_list(500)
    for m in materials:
        if "_id" in m:
            m["_id"] = str(m["_id"])
    return materials
