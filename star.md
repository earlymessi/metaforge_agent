# MetaForge 交付运行手册（FastAPI + MongoDB）

本文档用于交付环境的**快速上手与运行**，按步骤执行即可在本机启动 `tests/main.py` 提供的 **MetaForge MES（后端 FastAPI + MongoDB + 静态前端页面）**。

---

## 1. 环境要求

- **操作系统**：Windows 10/11（或 Windows Server，支持 PowerShell）
- **Python**：3.8+（建议 3.10/3.11/3.12）
- **MongoDB**：本机安装为 Windows 服务，默认端口 `27017`

> 本项目后端入口为 `tests/main.py`，默认监听 `http://127.0.0.1:8008`。

---

## 2. 启动 MongoDB（必须）

### 2.1 检查服务状态

在 PowerShell 执行：

```powershell
Get-Service -Name MongoDB
```

### 2.2 启动服务

如果 `Status` 不是 `Running`，执行：

```powershell
Start-Service MongoDB
```

### 2.3 验证端口监听

```powershell
Get-NetTCPConnection -LocalPort 27017 -State Listen
```

看到 `LocalAddress 127.0.0.1` 且 `State Listen` 即表示 MongoDB 正常监听。

---

## 3. 配置数据库连接（可选）

默认配置会连接：

- `MONGO_URL`: `mongodb://localhost:27017`
- `MONGO_DB_NAME`: `metaforge_mes`

如需修改（例如远程 MongoDB 或不同端口），在 PowerShell 设置环境变量：

```powershell
$env:MONGO_URL="mongodb://127.0.0.1:27017"
$env:MONGO_DB_NAME="metaforge_mes"
```

> 典型带账号密码连接串示例：  
> `mongodb://user:pass@127.0.0.1:27017/?authSource=admin`

---

## 4. 安装依赖与项目（首次运行必须）

进入项目根目录（包含 `pyproject.toml` 的目录），执行：

```powershell
pip install -e .
```

安装完成后会包含后端运行所需依赖：`fastapi`、`uvicorn`、`motor`、`pymongo` 等。

---

## 5. 启动后端（FastAPI）

进入 `tests` 目录并启动：

```powershell
cd .\tests
python .\main.py
```

正常启动会看到类似输出：

- `🚀 MetaForge Backend (FastAPI+Motor) running on http://127.0.0.1:8008`
- `✅ MongoDB 已连接: url=..., db=...`

---

## 6. 访问系统

在浏览器打开（需先完成「前端构建」，见 6.1）：

- **推荐（Vue3 新前端）**：`http://127.0.0.1:8008/new-ui/`  
  （路由 base 为 `/new-ui`，APS、报表等子路径如 `/new-ui/aps`）
- **根路径**：`http://127.0.0.1:8008/` — 同样返回构建后的 `index.html`，日常可与 `/new-ui/` 等价使用

若未构建前端，可能只看到 JSON：`{"message":"MetaForge Backend Running"}` 或旧版 `templates/index.html`。

---

## 6.1 前端页面启动说明

本项目前端为 **Vite + Vue3 + Element Plus**，构建产物输出到 `tests/templates/dist/`，由 **8008 端口后端统一托管**（唯一端口，`METAFORGE_PORT=8008`）。

- **交付/日常（推荐）**：`npm run build` 后只启动 `python main.py`，浏览器访问 **`http://127.0.0.1:8008/new-ui/`**。
- **开发联调（可选）**：`npm run dev` 后访问 `http://127.0.0.1:5173/`（仅改前端时用；**不是**必须步骤，5173 未启动不影响 8008 使用）。

### 前端构建（首次或前端改动后）

在项目根目录执行：

```powershell
cd .\frontend
npm install
npm run build
```

构建完成后会生成：`tests/templates/dist/`（后端直接托管）。

### 前端开发联调（可选）

```powershell
cd .\frontend
npm run dev
```

浏览器访问 `http://127.0.0.1:5173/`（`/api` 代理到 `8000`；若打不开，请直接用 8000，见上）。

**多智能体进度说明**：见 [`docs/多智能体开发进度.md`](docs/多智能体开发进度.md)。

---

## 7. 新增 API（近期）

| 接口 | 说明 |
|------|------|
| `POST /api/run/async` | 异步排程，返回 `task_id` |
| `GET /api/run/status/{task_id}` | 查询任务状态 |
| `GET /api/run/result/{task_id}` | 获取排程结果 |
| `POST /api/events/machine_breakdown_reschedule` | 设备故障局部重排 |
| `POST /api/events/due_date_reschedule` | 批量改交期后重排 |
| `GET/POST/DELETE /api/routing/*` | 工艺路线模板 |
| `GET /api/strategy/templates` | 策略权重模板 |
| `PUT /api/resources/config` | 更新能耗与 `downtime_blocks` 停机窗口 |
| `POST /api/materials/check_jobs` | 排程前 BOM 静态预检 |
| `POST /api/materials/predict` | 甘特 + 工单 BOM 库存仿真（body: schedule_data, jobs） |

### 多智能体与 HITL（Phase 0–3）

| 接口 | 说明 |
|------|------|
| `GET /api/tools/registry` | Tool 目录（供 Agent / 后期 LLM） |
| `GET /api/agents/registry` | 6 个业务 Agent 元数据 |
| `POST /api/orchestrator/run` | 按 message/intent 路由到唯一 Agent；响应含 `session_id`，`context.session_id` 可续跑 artifacts |
| `GET /api/orchestrator/session/{session_id}` | 查询会话摘要（artifact_keys、last_agent_id） |
| `POST /api/agents/{scheduling\|events\|kitting\|commitment\|whatif\|plans}/run` | 直连单 Agent（`pipeline` 为 scheduling 兼容别名） |
| `POST /api/db/propose_save` | 生成落库确认 token + preview |
| `POST /api/db/confirm_save` | 凭 token 写入 `schedule_result` |
| `POST /api/events/planned_downtime` 等 | 扩展事件重排（见进度文档） |

APS 页「排程并待确认落库」→ `scheduling` Agent（`persist_after`）→ 弹窗确认 → `confirm_save`。

### GLM 排程解析（Phase 5.1）

| 变量 | 说明 |
|------|------|
| `LLM_ENABLED` | `1` 启用（需 `ZHIPU_API_KEY`） |
| `ZHIPU_API_KEY` | 智谱 API Key，写在项目根目录 **`.env`**（已 gitignore） |
| `ZHIPU_MODEL` | 默认 `glm-4.5-air` |
| `LLM_FALLBACK` | 失败时 `rule`（回退 `SchedulingAgent.parse`） |

| 接口 | 说明 |
|------|------|
| `GET /api/llm/status` | 是否启用、是否有 Key |
| `POST /api/agent/schedule` | `message` + `parse_only` 可预览；响应含 `planner` |
| `POST /api/orchestrator/run` | 无 `intent` 时 GLM 路由；响应含 `router_planner`（`llm`/`rule`/`rule_fallback`） |
| `events.parse_event` | 异常自然语言 → `event_envelope`，含 `planner` |
| `/new-ui/assistant` | 智能助手对话页（Orchestrator + 6 Agent） |
| `LLM_PLAN_AGENTS` | 默认 `scheduling,events`，启用 Agent 内 LLM Plan |
| `SESSION_STORE` | `mongo` 持久化会话与 HITL token；`memory` 仅内存 |
| `GET /api/mcp/status` | MCP 外部工具状态（默认 `MCP_ENABLED=0`） |

停机窗口示例（写入 `downtime_blocks`）：

```json
{"machine_id": 0, "start": 10, "end": 20, "label": "保养"}
```

---

## 8. 快速验收（建议）

启动后用浏览器验证以下接口（直接访问即可）：

- **Benchmarks 列表**：`http://127.0.0.1:8008/api/benchmarks`
- **资源配置**：`http://127.0.0.1:8008/api/resources/config`

如返回 JSON 且无 500 错误，说明后端与 MongoDB 已基本联通。

> 说明：`/api/run` 现支持可选参数 `weights` 用于多目标综合评分（makespan/交期违约/能耗/负载均衡），用于前端报告页排序与对比。

---

## 8. 常见问题（排障）

### 8.1 `ECONNREFUSED 127.0.0.1:27017`

含义：**27017 端口无人监听**（最常见是 MongoDB 服务未启动）。

处理：

```powershell
Start-Service MongoDB
Get-NetTCPConnection -LocalPort 27017 -State Listen
```

### 8.2 启动时报 `MongoDB 连接失败`

检查项：

- `MONGO_URL` 是否正确（主机/端口/账号密码/authSource）
- MongoDB 是否允许本机连接（防火墙/绑定地址）

### 8.3 `Address already in use` / 8000 端口被占用

处理方式任选其一：

- 关闭占用 8000 的进程后重试
- 或修改 `tests/main.py` 底部的 `port=8000` 为其他端口（如 8080）

### 8.4 依赖安装失败

建议：

```powershell
python -m pip install -U pip
pip install -e .
```

---

## 9. 目录说明（交付相关）

- `tests/main.py`：FastAPI 后端入口（含 MongoDB 初始化、API 路由）
- `tests/templates/index.html`：前端页面（由 `/` 路由直接返回）
- `tests/data/benchmarks/`：基准算例数据（`/api/benchmarks` 会扫描此目录）

