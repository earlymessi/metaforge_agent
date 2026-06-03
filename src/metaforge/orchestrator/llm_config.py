"""LLM 功能开关（环境变量）。"""

from __future__ import annotations

import os


def llm_enabled() -> bool:
    return os.getenv("LLM_ENABLED") == "1" and bool((os.getenv("ZHIPU_API_KEY") or "").strip())


def llm_fallback_rule() -> bool:
    return os.getenv("LLM_FALLBACK", "rule") == "rule"
