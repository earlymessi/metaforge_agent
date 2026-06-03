"""机台编号展示（用户 1 起算 vs machine_id 0 起算）。"""

from __future__ import annotations


def machine_label_zh(machine_id: int) -> str:
    return f"{int(machine_id) + 1}号机"
