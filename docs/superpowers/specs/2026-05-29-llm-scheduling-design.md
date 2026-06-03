# Phase 5.1：GLM 排程意图解析（scheduling NL → 参数）

> **版本**：2026-05-29  
> **状态**：设计已定稿（待实施）  
> **父文档**：[`2026-05-29-mes-multi-agent-design.md`](2026-05-29-mes-multi-agent-design.md)  
> **前置**：Phase 0–4 已完成（Tool / 6 Agent / Router / Session / HITL）  
> **模型**：智谱 **glm-4.5-air**（OpenAI 兼容 Chat Completions）

---

## 1. 目标

在**不改变 Tool 执行链**的前提下，用 GLM 将车间自然语言解析为与现有一致的 `interpretation` 结构，再交给 `scheduling.run` 执行排程。

**第一期范围（YAGNI）：**

| 做 | 不做 |
|----|------|
| `scheduling.parse_intent` 内可选 GLM 解析 | Router / events / kitting 的 LLM |
| `/api/agent/schedule` 与 `/api/agents/scheduling/run` 共用解析 | LLM 生成 `PlanStep` 列表 |
| APS 一句式自然语言输入 + 可选 `parse_only` 预览 | 独立 Agent 聊天页 |
| 失败自动回退 `SchedulingAgent.parse()` | MCP |
| 白名单校验 solvers / strategy_id | 在 CI 中调用真实 GLM API |

---

## 2. 已确认的决策

| 问题 | 决策 |
|------|------|
| 第一期能力 | **B**：scheduling NL → 算法 / 策略 / 权重 |
| LLM 失败 | **A**：自动回退规则，响应标注 `planner: "rule_fallback"` |
| HTTP 入口 | **C**：`/api/agent/schedule` + `/api/agents/scheduling/run` 共用实现 |
| 前端 | **B**：APS 策略区增加自然语言输入框 |
| 实现结构 | **方案 1**：独立 `llm_client` + `llm_intent`，`parse_intent` 内分流 |

---

## 3. 架构

```text
┌─────────────────────────────────────────────────────────────┐
│  APS / API Client                                           │
│  message + optional solvers/weights (显式覆盖)                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
         ┌──────────────────┴──────────────────┐
         ▼                                      ▼
 POST /api/agent/schedule          POST /api/agents/scheduling/run
         │                                      │
         └──────────────────┬──────────────────┘
                            ▼
              scheduling.parse_intent (Tool)
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
   LLM_ENABLED=0      message 为空      LLM_ENABLED=1
   use_llm=false                         + message
         │                  │                  │
         └────────► SchedulingAgent.parse() ◄─┘
                  (rule)              │ fail/timeout
                                      ▼
                            llm_intent.parse_message()
                            (Zhipu glm-4.5-air)
                                      │
                                      ▼
                            validate + normalize
                                      │
                                      ▼
                         artifacts.interpretation
                         + planner: llm | rule_fallback
                            │
                            ▼
                    scheduling.run (不变)
```

**原则：**

- Tool 层仍禁止直接读 NL；NL 只在 `parse_intent` 的 Planner 分支处理。
- 显式 `params.solvers` / `weights` / `strategy_id` **优先于** LLM 输出（与现规则一致）。
- `scheduling.run`、`compare_solvers`、`solver_registry` **不修改契约**。

---

## 4. 模块划分

| 模块 | 路径 | 职责 |
|------|------|------|
| LLM HTTP 客户端 | `src/metaforge/orchestrator/llm_client.py` | OpenAI 兼容 `chat.completions`；超时；错误类型 |
| 排程意图 LLM | `src/metaforge/scheduling/llm_intent.py` | 构造 prompt；解析 JSON；校验；映射为 interpretation dict |
| 解析入口（已有） | `src/metaforge/tools/scheduling/parse_intent.py` | 分流 LLM / 规则；写 `artifacts.interpretation` |
| 规则解析（已有） | `src/metaforge/agent/scheduling_agent.py` | `SchedulingAgent.parse()` 作为回退与 LLM 关闭时路径 |
| 共享常量（已有） | `STRATEGY_TEMPLATES`、`get_solver_catalog()` | 注入 prompt 白名单 |

可选薄封装：

- `src/metaforge/scheduling/resolve_intent.py` — `resolve_schedule_intent(message, params, ctx) -> (interpretation, planner_meta)`，供 Tool 与 `/api/agent/schedule` 直接调用，避免重复。

---

## 5. 配置（环境变量）

**禁止**在代码、spec 示例或 git 中写入 API Key。仅通过环境变量或部署密钥注入。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_ENABLED` | `1` 启用 GLM 解析（需 Key） | `0` |
| `ZHIPU_API_KEY` | 智谱 API Key | 空 |
| `ZHIPU_BASE_URL` | OpenAI 兼容根 URL | `https://open.bigmodel.cn/api/paas/v4` |
| `ZHIPU_MODEL` | 模型 ID | `glm-4.5-air` |
| `LLM_TIMEOUT_SEC` | 请求超时（秒） | `30` |
| `LLM_FALLBACK` | 失败时行为 | `rule`（仅支持 `rule`；`fail` 留作后续） |
| `LLM_INTEGRATION` | 本地集成测试开关 | 未设置则不调真实 API |

**请求级覆盖：**

- `params.use_llm: false` — 强制走规则（调试 / A-B 对比）。

**启动检查（建议）：**

- `LLM_ENABLED=1` 且 `ZHIPU_API_KEY` 为空 → 启动日志 warning，运行时一律 `rule_fallback`。

---

## 6. GLM 调用约定

### 6.1 HTTP

- **Endpoint**：`POST {ZHIPU_BASE_URL}/chat/completions`
- **Headers**：`Authorization: Bearer {ZHIPU_API_KEY}`，`Content-Type: application/json`
- **Body**（与 OpenAI Chat 兼容）：

```json
{
  "model": "glm-4.5-air",
  "messages": [
    { "role": "system", "content": "<system_prompt>" },
    { "role": "user", "content": "<user_message>" }
  ],
  "temperature": 0.2,
  "response_format": { "type": "json_object" }
}
```

若 `response_format` 在 glm-4.5-air 上不可用，退化为在 system 中强调「只输出一个 JSON 对象」，并用正则/括号提取 JSON。

### 6.2 System Prompt 要点

1. 角色：MES 车间排程助手，只解析参数，不执行排程。  
2. 输出：**单个 JSON 对象**，字段见 §7。  
3. 注入精简白名单：  
   - `strategy_templates`: `[{id, name}, ...]`（来自 `STRATEGY_TEMPLATES`）  
   - `solvers`: `[{id, name_zh}, ...]`（来自 `get_solver_catalog()`，限制条数或按 family 分组摘要，控制 token）  
4. 规则提示：  
   - 「快速/先出结果」→ 倾向 `spt`  
   - 「对比/多算法」→ 2–4 个 solver  
   - 「交付/交期」→ `strategy_id: delivery`  
   - 「算例 ft10」→ `benchmark_file: ft10.txt`  
   - 「物料/齐套」→ `enforce_material: true`

### 6.3 User 内容

- 用户 `message`  
- 可选上下文一行：`input_mode: custom|file`（算例模式时不臆造 custom_data）

---

## 7. 输出 JSON 契约

LLM 必须输出（或经校验后补全）以下结构，与现 `interpretation` 对齐：

```json
{
  "solvers": ["ts", "spt"],
  "weights": {
    "makespan": 1.0,
    "weighted_tardiness_total": 0.5,
    "energy_cost": 0.05,
    "machine_busy_cv": 10.0
  },
  "strategy_id": "delivery",
  "strategy_name": "交付优先",
  "enforce_material": false,
  "benchmark_file": null,
  "summary_zh": "已按交付优先选择禁忌搜索与 SPT 对比。",
  "solver_match_notes": ["由 GLM 解析"],
  "strategy_match_note": "匹配策略模板 delivery"
}
```

**校验与归一化：**

| 字段 | 规则 |
|------|------|
| `solvers` | 非空；每项 `resolve_solver_id()` 成功；未知 id 剔除；空则 `["spt","ts"]` |
| `strategy_id` | 必须在 `STRATEGY_TEMPLATES`；否则 `balanced` |
| `weights` | 必须含设计文档四项目标键；缺省用所选 strategy 模板 weights |
| `enforce_material` | boolean |
| `benchmark_file` | null 或 `ft06.txt` 等形式；须存在于 benchmarks 目录（可选校验） |
| `summary_zh` | 非空字符串，≤ 200 字 |

校验失败 → 整段回退 `SchedulingAgent.parse()`。

**响应元数据**（写入 `interpretation` 或并列字段）：

```json
{
  "planner": "llm",
  "llm_model": "glm-4.5-air",
  "llm_latency_ms": 842
}
```

回退时：

```json
{
  "planner": "rule_fallback",
  "llm_error": "timeout"
}
```

`llm_error` 仅内部日志级别详情；给用户的 `summary_zh` 仍由规则或 LLM 正常生成。

---

## 8. `parse_intent` 分流逻辑

```python
def resolve_schedule_intent(params, ctx) -> InterpretationResult:
    message = params.get("message") or ctx.extras.get("message") or ""
    use_llm = (
        os.getenv("LLM_ENABLED") == "1"
        and params.get("use_llm") is not False
        and bool(message.strip())
        and os.getenv("ZHIPU_API_KEY")
    )
    if use_llm:
        try:
            return llm_intent.parse_message(message, params, ctx)
        except LlmIntentError as e:
            if os.getenv("LLM_FALLBACK", "rule") == "rule":
                return rule_parse_with_meta(message, params, ctx, llm_error=str(e))
            raise
    return rule_parse_with_meta(message, params, ctx)
```

**显式参数覆盖**（在 LLM 成功之后应用）：

- 若 `params.solvers` 非空 → 覆盖 `interpretation.solvers`  
- 若 `params.weights` 非空 → 覆盖 weights  
- 若 `params.strategy_id` 有效 → 覆盖 strategy 并同步 `strategy_name`  
- 若 `params.enforce_material` 非 None → 覆盖  

---

## 9. API 行为

### 9.1 `POST /api/agent/schedule`（已有）

- 有 `message` 且未 `parse_only`：先解析（GLM 或规则）→ `compare` / async。  
- `parse_only=true`：只返回 `interpretation` + `planner`，不跑排程。  
- 响应增加顶层或 `interpretation` 内 `planner` 字段。

### 9.2 `POST /api/agents/scheduling/run`（已有）

- `SchedulingAgentRunner.build_plan` 第一步仍为 `scheduling.parse_intent`。  
- Tool 内已含 GLM 分流，**无需**改 Plan 模板。  
- `AgentResponse.artifacts.interpretation` 含 `planner`。

### 9.3 可选诊断

- `GET /api/llm/status` — 返回 `enabled`, `model`, `has_api_key`（不返回 Key 值），便于运维。

---

## 10. 前端（APS）

**位置**：`frontend/src/views/APSView.vue` — 策略与运行侧栏。

**UI：**

- 多行输入 `scheduleMessage`：「用自然语言描述排程需求（可选）」  
- 按钮旁说明：填写后优先按语义选策略/算法；仍可手动勾选算法覆盖  
- 「预览解析」：调用 `parse_only=true`，弹窗展示 `interpretation.summary_zh`、`solvers`、`strategy_name`、`planner`  
- 「开始排程计算」：若 `scheduleMessage` 非空，写入 `message` 字段（`/api/run` 或 `/api/agent/schedule` 需确认 APS 当前调用链）

**APS 当前调用链核对（实施时）：**

- 若 APS 直接 `POST /api/run`，需在 payload 增加 `message` 并在后端 `CompareRequest` / 包装层先解析；**更简做法**：APS 改调 `/api/agent/schedule` 或 orchestrator `intent=schedule`，由后端统一解析后再跑 —— **实施计划 Task 中明确二选一，推荐 scheduling Agent 路径或扩展 `/api/run` 接受 message**。  
- **本 spec 推荐**：APS 排程按钮在存在 `scheduleMessage` 时调用 `/api/agent/schedule`（已有 interpretation 流程），无 message 时保持现有 `/api/run` 直连（手选算法）。

---

## 11. 错误处理

| 场景 | 行为 |
|------|------|
| 超时 | `rule_fallback`，`llm_error: timeout` |
| HTTP 4xx/5xx | `rule_fallback`，日志记 status |
| 非 JSON / schema 不符 | `rule_fallback` |
| Key 缺失 | 不调用 GLM，直接规则 |
| `use_llm=false` | 规则 |

**不向用户暴露** API Key、完整 prompt、原始 stack trace。

---

## 12. 测试策略

| 类型 | 内容 |
|------|------|
| 单元 | `llm_client` mock responses |
| 单元 | `llm_intent` 校验：非法 solver、缺 weights、合法 JSON |
| 集成 | `parse_intent`：`LLM_ENABLED=0` → 规则；mock GLM → `planner=llm` |
| 集成 | mock GLM 抛错 → `planner=rule_fallback` |
| Golden | ≥10 条中文话术 → mock LLM 返回固定 JSON → 断言 solvers/strategy_id |
| 可选 | `LLM_INTEGRATION=1` 本地脚本调真实 API（不进 CI） |
| 回归 | 现有 `test_agents_scheduling`、`test_scheduling_agent` 保持绿 |

---

## 13. 文件清单（实施参考）

| 操作 | 路径 |
|------|------|
| 新增 | `src/metaforge/orchestrator/llm_client.py` |
| 新增 | `src/metaforge/scheduling/__init__.py` |
| 新增 | `src/metaforge/scheduling/llm_intent.py` |
| 新增 | `src/metaforge/scheduling/resolve_intent.py`（推荐） |
| 修改 | `src/metaforge/tools/scheduling/parse_intent.py` |
| 修改 | `tests/main.py` — `/api/agent/schedule` 返回 `planner`；可选 `/api/llm/status` |
| 修改 | `frontend/src/views/APSView.vue` |
| 新增 | `tests/test_llm_intent.py` |
| 修改 | `docs/多智能体开发进度.md`、`star.md` — Phase 5.1 |
| 修改 | `pyproject.toml` — 若需 `httpx` 依赖（优先用 stdlib 或已有 requests） |

---

## 14. 非目标（Phase 5.1）

- Router LLM 分类  
- events NL → `event_envelope`  
- LLM 生成多步 Plan  
- 流式输出 / 多轮对话记忆（Session 仅存 artifacts，不存 chat history）  
- 将 GLM 用于客户话术生成（`delivery.customer_script` 仍为模板）

---

## 15. 后续 Phase（不在本期）

| Phase | 内容 |
|-------|------|
| 5.2 | Router + events `parse_event` LLM |
| 5.3 | Agent 内 LLM Plan（白名单 Tool steps） |
| 5.4 | AgentChatView + Orchestrator 统一对话 |
| 6 | MCP 适配器 |

---

## 16. 决策记录

| 日期 | 决策 |
|------|------|
| 2026-05-29 | Phase 5.1 仅 scheduling NL 解析，模型 glm-4.5-air |
| 2026-05-29 | 失败回退规则；双 API 入口共用；APS 一句式输入 |
| 2026-05-29 | API Key 仅环境变量，禁止入库 |

---

*文档结束 — 评审通过后使用 writing-plans 生成 `2026-05-29-llm-scheduling.md` 实施计划。*
