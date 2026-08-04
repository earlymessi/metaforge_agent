# MetaForge 交付运行手册（当前版）

按本文在本机启动 **MetaForge MES**：`tests/main.py`（FastAPI + MongoDB）托管 Vue3 前端。

> 默认地址：**`http://127.0.0.1:8008/go`**（会清掉旧 HTML 缓存并进入看板）  
> 日常入口：**`http://127.0.0.1:8008/new-ui/dashboard`**  
> 若「一打开还是旧页、刷新才变新」：先打开一次 `/go`，或浏览器里清除 `127.0.0.1:8008` 的网站数据。  
> 端口以代码为准：`METAFORGE_PORT` 默认 **8008**（`tests/main.py`）。README 里若仍写 8000，以本文与代码为准。

---

## 0. 一键启动（日常）

仓库根目录双击 **`start.bat`**，或在 PowerShell 执行：

```powershell
.\scripts\start_metaforge.ps1
```

脚本会：启动 MongoDB → 清理旧后端端口 →（缺 dist 时）构建前端 → 启动 `tests/main.py` → 自动打开浏览器。

常用参数：

```powershell
.\scripts\start_metaforge.ps1 -Rebuild    # 强制重编前端
.\scripts\start_metaforge.ps1 -Install    # 顺带 pip install -e . 与 npm install
.\scripts\start_metaforge.ps1 -NoBrowser  # 不自动开浏览器
```

等价手工步骤（对照）：

```powershell
# 1) MongoDB
Start-Service MongoDB

# 2) 后端依赖（首次或依赖变更后）
pip install -e .

# 3) 前端构建（首次或 frontend/ 有改动后）
cd .\frontend
npm install
npm run build
cd ..

# 4) 启动后端（会加载根目录 .env）
cd .\tests
python .\main.py
```

浏览器打开：

- **推荐（防旧缓存）**：http://127.0.0.1:8008/go
- 生产看板：http://127.0.0.1:8008/new-ui/dashboard
- 智能助手：http://127.0.0.1:8008/new-ui/assistant
- APS 排程：http://127.0.0.1:8008/new-ui/aps

启动成功时终端大致会出现：

```text
[OK] MongoDB 已连接: url=..., db=...
MetaForge Backend (FastAPI+Motor) running on http://127.0.0.1:8008
  统一入口: http://127.0.0.1:8008/go  →  /new-ui/dashboard
```

---

## 0.1 给别人演示（约 8～12 分钟）

**开场一句话：** MetaForge 把「排产 → AI 策略选方案 → 送入车间执行 → 异常自然语言重排」串在一条链路上。

### 演示前检查（1 分钟）

1. 双击 `start.bat` 或执行 `.\scripts\start_metaforge.ps1`
2. 浏览器打开 http://127.0.0.1:8008/go （首次务必用 `/go`，避免旧缓存）
3. 右侧「对比算法」至少勾选 **SPT、TS、GA、SA**（可再勾几个）
4. 若配置了 `.env` 里的 `ZHIPU_API_KEY`，助手/解析会更自然；没有也能规则跑通

### 主线剧本（建议按序）

| 步 | 页面 | 你做什么 | 你怎么讲 |
|----|------|----------|----------|
| 1 | APS → 自定义 | 点「加载示例」→「保存计划」 | 这是带交期/数量/BOM 的演示工单池，不是空模板 |
| 2 | APS 右侧 AI策略 | 粘贴话术：「交付优先，保证急单-钢架焊接按期，总完工尽量快」→「AI 协同排产运行」 | AI 先做订单/约束/资源三分析，再用你勾选的算法对比，综合得分**越低越好**；完成后会提示已同步到**分析报表 / 物料 / 能耗** |
| 3 | 结果区 / 报表 | 指候选表：排名 / 硬约束 / 对比结论；可先打开「分析报表」看多算法对比，再点「送入执行仿真」 | 推荐方案会生成代号计划（如 `PKG-…-TS`），并跳到看板开跑；**不必再点「开始排程计算」** |
| 4 | 生产看板 | 看甘特在走；可调仿真倍速 | 这是 MES 在线执行，不是静态报表 |
| 5 | 智能助手 | 输入：「3号机坏了4小时，帮我重排」 | 自然语言 → 故障解析 → R0/R1/R2：原计划 / 不重排推延 / 冻结后重排 |
| 6 | 影响弹窗 / 落库 | 打开 R0·R1·R2 表与甘特；若弹出确认落库，看三场景对比再点确认 | 强调：**R1 应变差、R2 应尽量救回来**；落库写的是 R2 |

### 备用话术（可直接念）

- AI 策略：`交付优先，保证急单-钢架焊接和急单-注塑罩壳按期，减少换型。`
- 故障重排：`3号机坏了4小时，帮我重排`
- 插单（可选）：`紧急插单，优先100，3号机5小时`

### 演示避坑

- 第一次页面还是旧的 → 打开一次 `/go` 或 Ctrl+F5
- AI 策略「无合法推荐」→ 先「加载示例」（工单必须有交期）
- AI 跑完后报表/资源仍空 → 确认提示「已同步 N 个算法方案…」，并 Ctrl+F5；勿再误以为必须点「开始排程计算」
- 落库弹窗里算法是 SPT/TS → 那是**本次执行基准算法**，不是又竞选了一遍
- 时间不够 → 跳过步骤 3 送仿真，直接在助手做故障重排（需看板已有执行基准；否则先完成 1～3）

---

## 1. 环境要求

| 项 | 要求 |
|----|------|
| OS | Windows 10/11（PowerShell） |
| Python | **3.10+**（建议 3.10 / 3.11 / 3.12） |
| MongoDB | Windows 服务，默认端口 `27017` |
| Node.js | 仅构建前端需要，建议 **18+** |

可选：项目根目录 `.env`（已 gitignore）。`main.py` 启动时会自动 `load_dotenv`。

---

## 2. MongoDB

```powershell
Get-Service -Name MongoDB
# 若未 Running：
Start-Service MongoDB
Get-NetTCPConnection -LocalPort 27017 -State Listen
```

默认连接：

| 变量 | 默认 |
|------|------|
| `MONGO_URL` | `mongodb://localhost:27017` |
| `MONGO_DB_NAME` | `metaforge_mes` |

```powershell
$env:MONGO_URL="mongodb://127.0.0.1:27017"
$env:MONGO_DB_NAME="metaforge_mes"
```

带账号示例：`mongodb://user:pass@127.0.0.1:27017/?authSource=admin`

---

## 3. 后端启动细节

```powershell
cd .\tests
python .\main.py
```

说明：

- 工作目录必须是 **`tests/`**（`uvicorn` 加载 `main:app`）。
- 会优先把仓库 `src/` 加入 `sys.path`，避免装到 site-packages 的旧包盖住新代码。
- 静态页：构建产物在 `tests/templates/dist/`，由后端托管；前端路由 base 为 **`/new-ui`**。

### 常用启动环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `METAFORGE_HOST` | `127.0.0.1` | 监听地址 |
| `METAFORGE_PORT` | `8008` | 监听端口 |
| `METAFORGE_RELOAD` | `0` | `1` 开启 uvicorn reload（开发慎用，易残留进程） |

```powershell
$env:METAFORGE_PORT="8080"
python .\main.py
# 访问 http://127.0.0.1:8080/new-ui/
```

### 端口被占用

```powershell
# 仓库脚本（推荐）
..\scripts\cleanup_backend.ps1
# 或在仓库根目录：
.\scripts\cleanup_backend.ps1
```

然后再 `python .\main.py`。也可改 `METAFORGE_PORT`。

---

## 4. 前端

### 4.1 交付 / 日常（推荐）

只构建一次，由 **8008 后端托管**：

```powershell
cd .\frontend
npm install
npm run build
```

- 输出目录：`tests/templates/dist/`（`vite.config.js` 的 `outDir`）
- 访问：`http://127.0.0.1:8008/new-ui/`（`/` 同样只托管该 dist，旧版 `templates/index.html` 已删除）
- `index.html` 响应带 `Cache-Control: no-store`，避免浏览器把旧入口缓存成「第一次还是旧页」

未构建时打开站点会返回 JSON：`{"error":"Frontend build not found. Run: cd frontend && npm run build"}`。

### 4.2 开发热更新（可选）

```powershell
# 终端 A：后端（8008）
cd .\tests
python .\main.py

# 终端 B：Vite
cd .\frontend
npm run dev
```

- 页面：http://127.0.0.1:5173/
- `/api` 代理到 `http://127.0.0.1:8008`（可用 `VITE_API_PROXY` 覆盖）
- **不是**交付必做步骤；交付只开 8008 即可。

---

## 5. 快速验收

后端起来后浏览器访问（应返回 JSON、无 500）：

| 检查 | URL |
|------|-----|
| Benchmarks | http://127.0.0.1:8008/api/benchmarks |
| 资源配置 | http://127.0.0.1:8008/api/resources/config |
| Agent 注册表 | http://127.0.0.1:8008/api/agents/registry |
| LLM 状态 | http://127.0.0.1:8008/api/llm/status |

页面冒烟：`/new-ui/`、`/new-ui/aps`、`/new-ui/assistant` 能打开。

---

## 6. 可选：GLM

根目录 `.env` 示例：

```env
LLM_ENABLED=1
ZHIPU_API_KEY=你的key
ZHIPU_MODEL=glm-4.5-air
LLM_FALLBACK=rule
```

| 变量 | 说明 |
|------|------|
| `LLM_ENABLED` | `1` 启用 |
| `ZHIPU_API_KEY` | 智谱 Key |
| `LLM_PLAN_AGENTS` | 默认 `scheduling`（其余业务域为固定编排） |
| `PLANNING_COLLAB_V1` | 默认 `1`；`0` 时 `/api/planning/collab/*` 返回 404 |
| `SESSION_STORE` | `mongo` / `memory` |
| `MCP_ENABLED` | 默认 `0` |

`GET /api/llm/status` 可查看是否启用、是否配置了 Key。

---

## 7. 排障

### 7.1 `ECONNREFUSED 127.0.0.1:27017`

```powershell
Start-Service MongoDB
Get-NetTCPConnection -LocalPort 27017 -State Listen
```

### 7.2 MongoDB 连接失败

检查 `MONGO_URL`、账号、`authSource`、防火墙。

### 7.3 端口占用 / 启动即退出

按 §3 运行 `scripts\cleanup_backend.ps1`，或更换 `METAFORGE_PORT`。

### 7.4 依赖安装失败

```powershell
python -m pip install -U pip
pip install -e .
```

### 7.5 只有 JSON、没有 Vue 页面

先 `cd frontend; npm run build`，再重启 `python main.py`。

### 7.6 前端改了但页面没变

重新 `npm run build`，并强制刷新浏览器（Ctrl+F5）。确认看的是 **8008/new-ui**，不是旧的 5173 会话。

---

## 8. 交付相关目录

| 路径 | 说明 |
|------|------|
| `tests/main.py` | 后端入口 |
| `tests/templates/dist/` | 前端构建产物 |
| `frontend/` | Vue3 源码 |
| `src/metaforge/` | 业务库（agents / collab / tools / planning） |
| `.env` | 本地密钥与开关（勿提交） |
| `scripts/cleanup_backend.ps1` | 清理占用后端端口的进程 |
| `docs/多智能体开发进度.md` | 能力与进度 |
| `docs/智能体功能清单.md` | Agent / API 清单 |

---

## 9. 能力索引（非启动必读）

六业务 Agent 均已 CollabBridge 同构；scheduling → `planning_collab`。看板异常重排走 `/api/events/*`，不依赖 Events Agent。

详细能力、S1–S4、Orchestrator API 见：

- [`docs/多智能体开发进度.md`](docs/多智能体开发进度.md)
- [`docs/智能体功能清单.md`](docs/智能体功能清单.md)
- [`README.md`](README.md)
