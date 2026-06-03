"""兼容旧导入：请使用 metaforge.orchestrator.llm。"""

from typing import Optional

from metaforge.orchestrator.llm.client import LlmClient, LlmClientError
from metaforge.orchestrator.llm.client import LlmClient as _Client


def chat_completion_json(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_sec: float = 30.0,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
):
    client = _Client(
        api_key=api_key,
        model=model,
        timeout_sec=timeout_sec,
        base_url=base_url or "https://open.bigmodel.cn/api/paas/v4",
    )
    return client.invoke_json(
        system=system_prompt,
        user=user_prompt,
        temperature=temperature,
    )


__all__ = ["LlmClient", "LlmClientError", "chat_completion_json"]
