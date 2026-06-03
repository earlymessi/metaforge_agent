# GLM 排程意图解析（Phase 5.1）Implementation Plan

> **已归档（2026-05-31）**：Phase 5.1 已实现。现行说明见 [`../../智能体功能清单.md`](../../智能体功能清单.md)。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用智谱 **glm-4.5-air** 将 APS 自然语言排程需求解析为 `interpretation`（solvers/weights/strategy），失败时回退 `SchedulingAgent.parse()`，双 API 入口共用。

**Architecture:** 新增 `llm_client`（OpenAI 兼容 HTTP，`requests`）与 `llm_intent`（prompt + JSON 校验）；`resolve_schedule_intent()` 统一分流；`scheduling.parse_intent` Tool 与 `/api/agent/schedule` 均调用该函数。APS 有 `message` 时改调 `/api/agent/schedule`，否则保持 `/api/run`。

**Tech Stack:** Python 3.8+、FastAPI、`requests`、现有 `SchedulingAgent` / `solver_registry` / Vue3 APS

**Spec:** [`docs/superpowers/specs/2026-05-29-llm-scheduling-design.md`](../specs/2026-05-29-llm-scheduling-design.md)

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `src/metaforge/orchestrator/llm_client.py` | 智谱 Chat Completions HTTP；超时；异常类型 |
| `src/metaforge/scheduling/llm_intent.py` | Prompt 构建、JSON 解析、白名单校验 |
| `src/metaforge/scheduling/resolve_intent.py` | `resolve_schedule_intent()` LLM/规则分流 + 显式参数覆盖 |
| `src/metaforge/tools/scheduling/parse_intent.py` | Tool handler 改为调用 `resolve_schedule_intent` |
| `tests/main.py` | `/api/agent/schedule` 返回 `planner`；`GET /api/llm/status` |
| `frontend/src/views/APSView.vue` | 自然语言输入、预览解析、有 message 时走 agent schedule |
| `tests/test_llm_client.py` | HTTP mock |
| `tests/test_llm_intent.py` | 校验与 golden |
| `tests/test_resolve_intent.py` | 分流与回退 |

---

## Task 1: `llm_client` + 失败测试

**Files:**
- Create: `src/metaforge/orchestrator/llm_client.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_llm_client.py
import json
from unittest.mock import MagicMock, patch

import pytest

from metaforge.orchestrator.llm_client import LlmClientError, chat_completion_json


def test_chat_completion_json_parses_message_content():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "choices": [{"message": {"content": '{"solvers":["spt"]}'}}]
    }
    with patch("metaforge.orchestrator.llm_client.requests.post", return_value=fake_resp):
        out = chat_completion_json(
            api_key="test-key",
            model="glm-4.5-air",
            system_prompt="sys",
            user_prompt="user",
            timeout_sec=5,
        )
    assert out == {"solvers": ["spt"]}


def test_chat_completion_json_raises_on_http_error():
    fake_resp = MagicMock()
    fake_resp.status_code = 401
    fake_resp.text = "unauthorized"
    with patch("metaforge.orchestrator.llm_client.requests.post", return_value=fake_resp):
        with pytest.raises(LlmClientError):
            chat_completion_json(
                api_key="k",
                model="glm-4.5-air",
                system_prompt="s",
                user_prompt="u",
                timeout_sec=5,
            )
```

- [ ] **Step 2: 运行确认 FAIL**

```powershell
cd D:\Users\Administrator\Desktop\软著\metaforge\tests
$env:PYTHONIOENCODING="utf-8"
python -m pytest test_llm_client.py -v
```

Expected: `ModuleNotFoundError` 或 `ImportError`

- [ ] **Step 3: 实现 `llm_client.py`**

```python
# src/metaforge/orchestrator/llm_client.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import requests


class LlmClientError(Exception):
  pass


def chat_completion_json(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_sec: float = 30.0,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    root = (base_url or os.getenv("ZHIPU_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
    url = f"{root}/chat/completions"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
    if resp.status_code >= 400:
        raise LlmClientError(f"http {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    if not content.strip():
        raise LlmClientError("empty content")
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise LlmClientError(f"invalid json: {e}") from e
```

- [ ] **Step 4: 运行测试 PASS**

```powershell
python -m pytest test_llm_client.py -v
```

---

## Task 2: `llm_intent` 校验与 normalize

**Files:**
- Create: `src/metaforge/scheduling/__init__.py`
- Create: `src/metaforge/scheduling/llm_intent.py`
- Test: `tests/test_llm_intent.py`

- [ ] **Step 1: 写失败测试（normalize）**

```python
# tests/test_llm_intent.py
from metaforge.scheduling.llm_intent import normalize_llm_payload


def test_normalize_maps_unknown_solver_and_strategy():
    raw = {
        "solvers": ["ts", "not_a_solver"],
        "strategy_id": "not_exist",
        "weights": {},
        "enforce_material": True,
        "summary_zh": "测试",
    }
    out = normalize_llm_payload(raw)
    assert "ts" in out["solvers"]
    assert "not_a_solver" not in out["solvers"]
    assert out["strategy_id"] in ("balanced", "delivery", "throughput", "cost", "balance_load")
    assert "makespan" in out["weights"]
    assert out["planner"] == "llm"
```

- [ ] **Step 2: 运行 FAIL** — `python -m pytest test_llm_intent.py::test_normalize_maps_unknown_solver_and_strategy -v`

- [ ] **Step 3: 实现 `normalize_llm_payload` + `build_system_prompt` + `parse_message_with_llm`（mock client）**

要点：
- `normalize_llm_payload(raw) -> dict`：调用 `resolve_solver_id`、`_STRATEGY_BY_ID`、补全四项目标 weights、默认 solvers `["spt","ts"]`
- `parse_message_with_llm(message, *, params, benchmark_file=None) -> dict`：拼 prompt → `chat_completion_json` → normalize → 附加 `planner`, `llm_model`, `llm_latency_ms`
- `build_system_prompt()`：嵌入 `STRATEGY_TEMPLATES` 与 `get_solver_catalog()["solvers"]` 前 20 条 id+name_zh

- [ ] **Step 4: mock `chat_completion_json` 测 `parse_message_with_llm`**

```python
@patch("metaforge.scheduling.llm_intent.chat_completion_json")
def test_parse_message_with_llm(mock_chat):
    mock_chat.return_value = {
        "solvers": ["spt"],
        "strategy_id": "delivery",
        "weights": STRATEGY_TEMPLATES[1]["weights"],
        "enforce_material": False,
        "summary_zh": "交付优先用SPT",
    }
    with patch.dict("os.environ", {"ZHIPU_API_KEY": "k", "ZHIPU_MODEL": "glm-4.5-air"}):
        out = parse_message_with_llm("交付优先快速排程")
    assert out["planner"] == "llm"
    assert out["solvers"] == ["spt"]
```

- [ ] **Step 5: PASS** — `python -m pytest test_llm_intent.py -v`

---

## Task 3: `resolve_schedule_intent` 分流

**Files:**
- Create: `src/metaforge/scheduling/resolve_intent.py`
- Test: `tests/test_resolve_intent.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_resolve_intent.py
import os
from unittest.mock import patch

from metaforge.scheduling.resolve_intent import resolve_schedule_intent


def test_resolve_uses_rule_when_llm_disabled():
    os.environ["LLM_ENABLED"] = "0"
    result = resolve_schedule_intent(
        {"message": "禁忌搜索排程"},
        extras={},
        benchmark_file=None,
    )
    assert result["planner"] in ("rule", "rule_fallback")
    assert result["solvers"]


@patch("metaforge.scheduling.resolve_intent.parse_message_with_llm")
def test_resolve_uses_llm_when_enabled(mock_llm):
    os.environ["LLM_ENABLED"] = "1"
    os.environ["ZHIPU_API_KEY"] = "test"
    mock_llm.return_value = {
        "solvers": ["spt"],
        "strategy_id": "balanced",
        "strategy_name": "综合平衡",
        "weights": {"makespan": 1.0, "weighted_tardiness_total": 0.5, "energy_cost": 0.05, "machine_busy_cv": 10.0},
        "summary_zh": "ok",
        "planner": "llm",
        "enforce_material": False,
        "benchmark_file": None,
        "solver_match_notes": [],
        "strategy_match_note": "",
    }
    result = resolve_schedule_intent({"message": "随便排"}, extras={})
    assert result["planner"] == "llm"


@patch("metaforge.scheduling.resolve_intent.parse_message_with_llm", side_effect=Exception("timeout"))
def test_resolve_fallback_on_llm_error(mock_llm):
    os.environ["LLM_ENABLED"] = "1"
    os.environ["ZHIPU_API_KEY"] = "test"
    os.environ["LLM_FALLBACK"] = "rule"
    result = resolve_schedule_intent({"message": "禁忌搜索"}, extras={})
    assert result["planner"] == "rule_fallback"
    assert "llm_error" in result
```

- [ ] **Step 2: 实现 `resolve_schedule_intent`**

```python
def resolve_schedule_intent(params, extras=None, benchmark_file=None) -> Dict[str, Any]:
    message = (params.get("message") or (extras or {}).get("message") or "").strip()
    use_llm = (
        os.getenv("LLM_ENABLED") == "1"
        and params.get("use_llm") is not False
        and bool(message)
        and bool(os.getenv("ZHIPU_API_KEY"))
    )
    if use_llm:
        try:
            data = parse_message_with_llm(message, params=params, benchmark_file=benchmark_file)
        except Exception as e:
            if os.getenv("LLM_FALLBACK", "rule") != "rule":
                raise
            data = _rule_interpretation(message, params, benchmark_file, llm_error=str(e))
            data["planner"] = "rule_fallback"
            return _apply_explicit_overrides(data, params)
        return _apply_explicit_overrides(data, params)
    data = _rule_interpretation(message, params, benchmark_file)
    data["planner"] = "rule"
    return _apply_explicit_overrides(data, params)
```

`_rule_interpretation` 包装现有 `SchedulingAgent().parse()` → interpretation dict（与 `parse_intent.py` 现逻辑一致）。

- [ ] **Step 3: PASS** — `python -m pytest test_resolve_intent.py -v`

---

## Task 4: 接入 `parse_intent` Tool

**Files:**
- Modify: `src/metaforge/tools/scheduling/parse_intent.py`

- [ ] **Step 1: 修改 handler 调用 `resolve_schedule_intent`**

将 `_handle_parse_intent` 内 `SchedulingAgent().parse(...)` 替换为：

```python
from metaforge.scheduling.resolve_intent import resolve_schedule_intent

data = resolve_schedule_intent(
    params,
    extras=ctx.extras,
    benchmark_file=params.get("benchmark_file") or ctx.benchmark_file,
)
data["compare_kwargs"] = {
    "solvers": data["solvers"],
    "weights": data["weights"],
    "enforce_material": data["enforce_material"],
    "benchmark_file": data.get("benchmark_file"),
}
```

- [ ] **Step 2: 运行现有测试**

```powershell
python -m pytest test_tools_scheduling.py test_agents_scheduling.py -v
```

Expected: PASS

---

## Task 5: `/api/agent/schedule` + `/api/llm/status`

**Files:**
- Modify: `tests/main.py`

- [ ] **Step 1: 抽取 `_interpretation_from_agent_schedule(req)` 使用 `resolve_schedule_intent`**

在 `scheduling_agent_run` 中，将 `_scheduling_agent.parse(...)` 块改为：

```python
from metaforge.scheduling.resolve_intent import resolve_schedule_intent

interpretation = resolve_schedule_intent(
    {
        "message": req.message,
        "solvers": req.solvers,
        "weights": req.weights,
        "strategy_id": req.strategy_id,
        "enforce_material": req.enforce_material,
        "benchmark_file": benchmark_file,
    },
    extras={},
    benchmark_file=bench,
)
```

保留 `interpretation` 字段结构；响应增加 `"planner": interpretation.get("planner")`。

- [ ] **Step 2: 添加 `GET /api/llm/status`**

```python
@app.get("/api/llm/status")
async def llm_status():
    import os
    return {
        "enabled": os.getenv("LLM_ENABLED") == "1",
        "model": os.getenv("ZHIPU_MODEL", "glm-4.5-air"),
        "has_api_key": bool(os.getenv("ZHIPU_API_KEY")),
        "fallback": os.getenv("LLM_FALLBACK", "rule"),
    }
```

- [ ] **Step 3: 冒烟**

```powershell
python -m pytest test_api_smoke.py -v -k "multi_agent"
```

手动（可选，`LLM_INTEGRATION=1`）：

```powershell
$env:LLM_ENABLED="1"
$env:ZHIPU_API_KEY="<your-key>"
curl -X POST http://127.0.0.1:8000/api/agent/schedule -H "Content-Type: application/json" -d "{\"message\":\"交付优先用禁忌搜索\",\"parse_only\":true,\"custom_data\":[...]}"
```

---

## Task 6: APS 前端

**Files:**
- Modify: `frontend/src/views/APSView.vue`

- [ ] **Step 1: 增加状态与 UI**

在策略区 `weights-panel` 上方增加：

```vue
<el-form-item label="自然语言排程（可选）">
  <el-input
    v-model="scheduleMessage"
    type="textarea"
    :rows="2"
    placeholder="例如：交付优先，对比禁忌搜索和SPT"
  />
</el-form-item>
<el-button size="small" :disabled="!scheduleMessage" @click="previewScheduleIntent">
  预览解析
</el-button>
```

`scheduleMessage = ref('')`

- [ ] **Step 2: `previewScheduleIntent`**

```javascript
async function previewScheduleIntent() {
  const payload = {
    message: scheduleMessage.value,
    custom_data: customJobs.value.map((j) => mapJobPayload(j)),
    parse_only: true,
    solvers: selectedSolvers.value,
    weights: { ...weights },
  }
  const { data } = await api.post('/api/agent/schedule', payload)
  ElMessageBox.alert(
    `${data.interpretation?.summary_zh || ''}\n\nplanner: ${data.planner || data.interpretation?.planner}\nsolvers: ${(data.interpretation?.solvers || []).join(', ')}`,
    '解析预览',
  )
}
```

- [ ] **Step 3: 修改 `run()` — 有 message 时走 agent schedule**

```javascript
async function run() {
  store.computing = true
  try {
    if (scheduleMessage.value?.trim() && inputMode.value === 'custom') {
      const agentPayload = {
        message: scheduleMessage.value.trim(),
        custom_data: customJobs.value.map((j) => mapJobPayload(j)),
        solvers: selectedSolvers.value,
        weights: { ...weights },
        random_seed: randomSeed.value != null ? Number(randomSeed.value) : undefined,
        enforce_material: enforceMaterial.value,
      }
      const { data } = await api.post('/api/agent/schedule', agentPayload)
      if (data?.error) throw new Error(data.error)
      if (data.status === 'need_data') throw new Error(data.message_zh || '缺少数据')
      store.setResults(data.data || data.results)
      // ... material_check 等同原逻辑
      router.push('/reports')
      return
    }
    // 原有 postRunMaybeAsync 路径不变
```

根据 `/api/agent/schedule` 实际返回字段调整（`data` vs `results` — 读 `scheduling_agent_run` 返回体）。

- [ ] **Step 4: 构建**

```powershell
cd D:\Users\Administrator\Desktop\软著\metaforge\frontend
npm run build
```

---

## Task 7: 文档与回归

**Files:**
- Modify: `docs/多智能体开发进度.md`
- Modify: `star.md`

- [ ] **Step 1: 更新进度文档 Phase 5.1 为已完成（实施后勾选）**

- [ ] **Step 2: `star.md` 增加环境变量说明**

```markdown
| `LLM_ENABLED` | 1 启用 GLM 排程解析 |
| `ZHIPU_API_KEY` | 智谱 API Key（勿提交 git） |
| `ZHIPU_MODEL` | 默认 glm-4.5-air |
```

- [ ] **Step 3: 全量回归**

```powershell
cd tests
python -m pytest test_llm_client.py test_llm_intent.py test_resolve_intent.py test_tools_scheduling.py test_agents_scheduling.py test_orchestrator_e2e.py test_api_smoke.py -q
```

Expected: 全部 PASS（不含 `LLM_INTEGRATION` 真实 API）

---

## Spec 覆盖自检

| Spec 要求 | Task |
|-----------|------|
| glm-4.5-air + 环境变量 | 1, 5 |
| 失败回退规则 + planner | 3 |
| 双 API 共用 | 4, 5 |
| APS NL 输入 + parse_only | 6 |
| 白名单校验 | 2 |
| 显式 params 覆盖 | 3 |
| 测试 mock、无 CI 真实 API | 1–3, 7 |
| `/api/llm/status` | 5 |
| 不写 Key 入库 | 全文 |

---

## 执行方式

Plan 已保存至 `docs/superpowers/plans/2026-05-29-llm-scheduling.md`。

**两种执行选项：**

1. **Subagent-Driven（推荐）** — 按 Task 派发子 agent，每 Task 完成后 review  
2. **Inline Execution** — 在本会话用 executing-plans 按 Task 批量实现并设检查点  

你更希望用哪种方式开始实施？
