"""将 Python 对象转为可写入 MongoDB 的结构。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def to_bson_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value
    if isinstance(value, dict):
        return {str(k): to_bson_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_bson_safe(v) for v in value]
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return to_bson_safe(value.model_dump(mode="json"))
    if hasattr(value, "dict") and callable(value.dict):
        return to_bson_safe(value.dict())
    if hasattr(value, "__dict__"):
        return to_bson_safe(vars(value))
    return str(value)
