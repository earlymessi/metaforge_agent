"""Chat 模型封装（对标 LangChain ChatModel.invoke）。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


class LlmClientError(Exception):
    """LLM HTTP 或响应解析失败。"""


@dataclass
class LlmClient:
    api_key: str
    model: str
    timeout_sec: float = 30.0
    base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    @classmethod
    def from_env(cls) -> LlmClient:
        key = (os.getenv("ZHIPU_API_KEY") or "").strip()
        if not key:
            raise LlmClientError("ZHIPU_API_KEY not set")
        return cls(
            api_key=key,
            model=os.getenv("ZHIPU_MODEL", "glm-4.5-air"),
            timeout_sec=float(os.getenv("LLM_TIMEOUT_SEC", "30")),
            base_url=(os.getenv("ZHIPU_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4").rstrip("/"),
        )

    def invoke_json(
        self,
        *,
        system: str,
        user: str,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        temp = temperature if temperature is not None else float(os.getenv("LLM_TEMPERATURE", "0.2"))
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temp,
            "response_format": {"type": "json_object"},
        }
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_sec,
        )
        if resp.status_code >= 400:
            raise LlmClientError(f"http {resp.status_code}: {resp.text[:300]}")
        choices = resp.json().get("choices") or []
        if not choices:
            raise LlmClientError("no choices in response")
        content = (choices[0].get("message") or {}).get("content") or ""
        if not str(content).strip():
            raise LlmClientError("empty content")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise LlmClientError(f"invalid json: {e}") from e
        if not isinstance(parsed, dict):
            raise LlmClientError("json root must be object")
        return parsed
