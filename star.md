# MetaForge 交付运行手册（FastAPI + MongoDB）

本文档用于交付环境的**快速上手与运行**，按步骤执行即可在本机启动 `tests/main.py` 提供的 **MetaForge MES（后端 FastAPI + MongoDB + 静态前端页面）**。

---

## 1. 环境要求

- **操作系统**：Windows 10/11（或 Windows Server，支持 PowerShell）
- **Python**：3.10+（建议 3.10 / 3.11 / 3.12）
- **MongoDB**：本机安装为 Windows 服务，默认端口 `27017`
- **Node.js**（仅构建前端时需要）：建议 18+

> 本项目后端入口为 `tests/main.py`，默认监听 **`http://127.0.0.1:8008`**（可用环境变量 `METAFORGE_PORT` 修改）。

---

## 2. 启动 MongoDB（必须）

### 2.1 检查服务状态

```powershell
Get-Service -Name MongoDB
```

### 2.2 启动服务

如果 `Status` 不是 `Running`：

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

默认配置：

- `MONGO_URL`: `mongodb://localhost:27017`
- `MONGO_DB_NAME`: `metaforge_mes`

修改示例：

```powershell
$env:MONGO_URL="mongodb://127.0.0.1:27017"
$env:MONGO_DB_NAME="metaforge_mes"
```

> 带账号密码示例：`mongodb://user:pass@127.0.0.1:27017/?authSource=admin`

---

## 4. 安装依赖（首次运行必须）

进入项目根目录（含 `pyproject.toml`）：

```powershell
pip install -e .
```

会安装后端依赖：`fastapi`、`uvicorn`、`motor`、`pymongo` 等。

---

## 5. 启动后端（FastAPI）

```powershell
cd .\tests
python .\main.py
```

正常启动会看到类似输出：

- `MetaForge Backend ... running on http://127.0.0.1:8008`
- `MongoDB 已连接: ...`

改端口：

```powershell
$env:METAFORGE_PORT="8080"
python .\main.py
```

---

## 6. 访问系统

需先完成「前端构建」（见 6.1）：

- **推荐**：`http://127.0.0.1:8008/new-ui/`（路由 base 为 `/new-ui`）
- **根路径**：`http://127.0.0.1:8008/` — 同样返回构建后的 `index.html`

若未构建前端，可能只看到 JSON：`{"message":"MetaForge Backend Running"}`。

---

## 6.1 前端页面

前端为 **Vite + Vue3 + Element Plus**，构建产物在 `tests/templates/dist/`，由 **8008 后端统一托管**。

- **交付/日常（推荐）**：`npm run build` 后只启动 `python main.py`，访问 `http://127.0.0.1:8008/new-ui/`
- **开发联调（可选）**：`npm run dev` → `http://127.0.0.1:5173/`（`/api` 代理到后端；**非必须**）

### 前端构建（首次或前端改动后）

```powershell
cd .\frontend
npm install
npm run build
```

产物：`tests/templates/dist/`。

### 前端开发联调（可选）

```powershell
cd .\frontend
npm run dev
```

---

## 7. 当前能力速览（交付相关）

更完整说明见：

- [`docs/多智能体开发进度.md`](docs/多智能体开发进度.md)
- [`docs/智能体功能清单.md`](docs/智能体功能清单.md)
- 仓库根目录 [`README.md`](README.md)

### 7.1 六业务 Agent（同构后）

| Agent | 主路径 | 入口 |
|-------|--------|------|
| `scheduling` | `SchedulingCollabBridge` → `planning_collab` | `/api/agents/scheduling/run`、Orchestrator |
| `events` | `EventsCollabBridge` → `events_collab` | `/api/agents/events/run`；看板另有 `/api/events/*` |
| `kitting` | `KittingCollabBridge` → `kitting_collab` | `/api/agents/kitting/run` |
| `commitment` | `CommitmentCollabBridge` → `commitment_collab` | `/api/agents/commitment/run` |
| `whatif` | `WhatifCollabBridge` → `whatif_collab` | `/api/agents/whatif/run` |
| `plans` | `PlansCollabBridge` → `plans_collab` | `/api/agents/plans/run` |

> 旧 `*AgentRunner` 主路径已删除。助手页走 Orchestrator SSE：`/api/orchestrator/stream`。

### 7.2 规划 / 仿真（S1–S4）

| 能力 | 说明 |
|------|------|
| Planning Strategy（S1） | `/api/planning/run`、策略 HITL、`strategy_trace` |
| Planning Collab（S2） | `/api/planning/collab/{analyze,run,runs/{id}}`；Flag `PLANNING_COLLAB_V1`（默认开；关则 collab API 404） |
| 前端三模式（S3） | APS `PlanningWorkbench`：模板 / 参数 / AI + Package 结果 |
| 仿真与对比（S4） | Package→MES 仿真、扰动剧本、`/compare` 三甘特 + JSON/PDF |

### 7.3 常用 API

| 接口 | 说明 |
|------|------|
| `POST /api/orchestrator/run` | 按 message/intent 路由到唯一 Agent |
| `POST /api/orchestrator/stream` | 同上，SSE 推送思考过程 |
| `GET /api/agents/registry` | 6 个业务 Agent 元数据 |
| `GET /api/tools/registry` | Tool 目录 |
| `POST /api/agents/{id}/run` | 直连单 Agent |
| `POST /api/events/*_reschedule` | 看板异常重排（R0/R1/R2），不依赖 Events Agent |
| `POST /api/db/propose_save` / `confirm_save` | 排程落库 HITL |
| `GET /api/llm/status` | GLM 开关与 Key 状态 |
| `GET /api/mcp/status` | MCP 状态（默认关闭） |

### 7.4 GLM / 会话环境变量

| 变量 | 说明 |
|------|------|
| `LLM_ENABLED` | `1` 启用（需 `ZHIPU_API_KEY`，写在根目录 `.env`） |
| `ZHIPU_API_KEY` | 智谱 API Key |
| `ZHIPU_MODEL` | 默认 `glm-4.5-air` |
| `LLM_FALLBACK` | 失败时 `rule` 回退 |
| `LLM_PLAN_AGENTS` | 默认 `scheduling`（其余域已固定编排，不进 LLM Tool-plan） |
| `PLANNING_COLLAB_V1` | 默认 `1`；仅闸 collab HTTP API |
| `SESSION_STORE` | `mongo` 持久化会话；`memory` 仅内存 |
| `MCP_ENABLED` | 默认 `0` |

智能助手页：`/new-ui/assistant`。

---

## 8. 快速验收

启动后浏览器访问：

- Benchmarks：`http://127.0.0.1:8008/api/benchmarks`
- 资源配置：`http://127.0.0.1:8008/api/resources/config`
- Agent 注册表：`http://127.0.0.1:8008/api/agents/registry`

返回 JSON 且无 500，说明后端与 MongoDB 基本联通。

---

## 9. 常见问题

### 9.1 `ECONNREFUSED 127.0.0.1:27017`

MongoDB 未监听。处理：

```powershell
Start-Service MongoDB
Get-NetTCPConnection -LocalPort 27017 -State Listen
```

### 9.2 `MongoDB 连接失败`

检查 `MONGO_URL`、账号密码、`authSource`、防火墙/绑定地址。

### 9.3 端口被占用

默认 **8008**。处理任选其一：

```powershell
$env:METAFORGE_PORT="8080"
```

或结束占用该端口的进程后重试。

### 9.4 依赖安装失败

```powershell
python -m pip install -U pip
pip install -e .
```

### 9.5 只看到 JSON、没有 Vue 页面

未执行前端构建。按 §6.1 `npm run build` 后重启后端。

---

## 10. 目录说明（交付相关）

| 路径 | 说明 |
|------|------|
| `tests/main.py` | FastAPI 入口（MongoDB、API、静态托管） |
| `tests/templates/dist/` | 前端构建产物（交付访问） |
| `frontend/` | Vue3 源码 |
| `src/metaforge/` | 核心库（agents / collab / tools / planning） |
| `tests/data/benchmarks/` | 基准算例（`/api/benchmarks`） |
| `docs/` | 进度、功能清单、规格与计划 |
