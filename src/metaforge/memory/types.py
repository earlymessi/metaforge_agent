"""记忆类型与键名约定（工作记忆 / 语义偏好 / 情景日志）。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Tuple

# 工作记忆：会话内、多轮 HITL / 澄清
WORKING_KEY_INSERT_JOB = ("events", "insert_job_intake")

# artifacts 兼容别名（历史 Tool 仍写 artifacts）
ARTIFACT_ALIASES: Dict[Tuple[str, str], str] = {
    WORKING_KEY_INSERT_JOB: "insert_job_intake",
}


class MemoryScope(str, Enum):
    WORKING = "working"
    SCHEDULING = "scheduling"  # 排程语义+澄清+情景（原 scheduling_memory）
    EPISODIC = "episodic"


def working_key(namespace: str, key: str) -> str:
    return f"{namespace}:{key}"


def empty_memory_store() -> Dict[str, Any]:
    return {"working": {}, "scheduling": {}, "episodic": []}
