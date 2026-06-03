"""Prompt 工程模板：角色 + 范围 + 格式 + 工具边界 + few-shots。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple


def build_structured_prompt(
    *,
    role: str,
    scope: str,
    output_format: str,
    tool_scope: Optional[str] = None,
    business_rules: Optional[str] = None,
    few_shots: Optional[Sequence[Tuple[str, str]]] = None,
    closing: str = "只输出 JSON，不要 markdown 或其他文字。",
) -> str:
    """组装 system prompt（自上而下 Agent 解析层统一结构）。"""
    parts = [f"## 角色\n{role.strip()}", f"## 职责范围\n{scope.strip()}"]
    if tool_scope:
        parts.append(f"## 可用工具/枚举边界\n{tool_scope.strip()}")
    if business_rules:
        parts.append(f"## 业务规则\n{business_rules.strip()}")
    parts.append(f"## 输出格式\n{output_format.strip()}")
    if few_shots:
        lines = ["## 参考示例（格式与推理方式，非当前请求）"]
        for i, (inp, out) in enumerate(few_shots, 1):
            lines.append(f"示例{i} 输入：{inp}")
            lines.append(f"示例{i} 输出：{out}")
        parts.append("\n".join(lines))
    parts.append(closing)
    return "\n\n".join(parts)


def build_user_message(
    message: str,
    *,
    context_lines: Optional[List[str]] = None,
    prefix: str = "当前用户消息",
) -> str:
    parts = [f"{prefix}：{(message or '').strip() or '（无）'}"]
    for line in context_lines or []:
        if line:
            parts.append(line)
    return "\n".join(parts)


def json_line(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
