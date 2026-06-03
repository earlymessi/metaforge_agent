"""Tool 层基础类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

ToolHandler = Callable[[Dict[str, Any], "ToolContext"], "ToolResult"]


@dataclass
class ToolContext:
    """执行 Tool 时的共享上下文（由 Agent 填充）。"""

    custom_data: Optional[List[Any]] = None
    benchmark_file: Optional[str] = None
    plan_id: Optional[str] = None
    weights: Optional[Dict[str, float]] = None
    enforce_material: bool = False
    random_seed: Optional[int] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    artifacts_key: Optional[str] = None


@dataclass
class ToolSpec:
    name: str
    description_zh: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    handler: ToolHandler
