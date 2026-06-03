"""llm_client 测试。"""

from unittest.mock import MagicMock, patch

import pytest

from metaforge.orchestrator.llm.client import LlmClient, LlmClientError


def test_invoke_json_parses_message_content():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "choices": [{"message": {"content": '{"solvers":["spt"]}'}}]
    }
    client = LlmClient(api_key="test-key", model="glm-4.5-air", timeout_sec=5)
    with patch("metaforge.orchestrator.llm.client.requests.post", return_value=fake_resp) as post:
        out = client.invoke_json(system="sys", user="user", temperature=0.1)
    assert out == {"solvers": ["spt"]}
    assert post.call_args.kwargs["json"]["temperature"] == 0.1


def test_invoke_json_raises_on_http_error():
    fake_resp = MagicMock()
    fake_resp.status_code = 401
    fake_resp.text = "unauthorized"
    client = LlmClient(api_key="k", model="glm-4.5-air", timeout_sec=5)
    with patch("metaforge.orchestrator.llm.client.requests.post", return_value=fake_resp):
        with pytest.raises(LlmClientError):
            client.invoke_json(system="s", user="u")
