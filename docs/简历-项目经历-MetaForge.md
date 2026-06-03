# 简历项目经历 — Multi-Agent 制造排程（对齐个人版式）

> 版式参考：项目名 + 时间 + 技术栈 + 项目背景 + 工作内容 + 效果评测。  
> 数据来源于仓库代码与 pytest；**无实测数据的指标未写入**。请按实际参与周期修改时间。  
> **推荐项目名（含 Agent，不含产品代号）：** 见文末「项目命名备选」。

---

## 版本一（投递 AI Agent / 大模型应用）

**Multi-Agent 制造排程智能体系统**  
（备选：`车间 Multi-Agent 排产与异常调度系统` / `制造领域 Multi-Agent 编排平台`）
**2025/10 – 2026/05**（多智能体阶段；全项目可写 2025/06 – 2026/05）

**技术栈：** Python、FastAPI、Uvicorn、自研多智能体编排器、智谱 GLM（OpenAI 兼容 Chat Completions）、自研 `LlmNode` 任务链（对标 LangGraph/LangChain 节点思想，**未引入 LangGraph/LangChain SDK**）、Plan-and-Solve、白名单 Tool 调用、ReAct/Reflect、JSON 结构化解析、SSE、MongoDB（Motor）、Vue3/Vite/Element Plus、Pydantic、pytest

**项目背景：** 面向离散制造车间 Job Shop 排产与生产执行场景，针对传统 APS「功能分散、口语难用、异常重排与落库割裂」等问题，从零搭建 **6 专责 Agent + 统一编排器**，覆盖【意图路由—Tool 规划—确定性执行—会话落库】链路；在 **6 类业务意图、30 个 Tool、20 条标准车间话术** 上完成规则回归与 GLM 联调冒烟验证。

**工作内容：**

1、设计 **6 专责 Agent**（智能排程 / 异常重排 / 齐套 / 交期承诺 / 方案对比 / 计划管理）+ 统一编排器，单请求 **仅路由 1 个 Agent**；实现 `POST /api/orchestrator/stream` **SSE 流式**输出 Route→Plan→Parse→Execute→Summarize 全链路轨迹，并提供 `/preview` 仅预览执行计划。

2、构建 **GLM 优先 + 规则兜底** 的 LLM 层：落地 **9 类 Prompt 节点**（router、排程/事件解析、plan、计划库意图、插单续聊、ReAct、Reflect、summarize）；配套 JSON 结构化输出校验；GLM 超时自动 **rule_fallback**；设计 **4 组路由 Guard**（计划库、缺料齐套、改交期重排、工单延期问询）降低误分到排程/交期 Agent。

3、实现 **Plan-and-Solve** 与白名单 **30 个 Tool**：排程侧对接 **14 种求解器 + 6 种策略模板** 的自然语言解析（`parse_intent` / `resolve_schedule_intent`）；异常侧覆盖 **8 类动态事件**，统一重排内核输出 **R0/R1/R2** 三场景甘特与 `impact_report`；排程落库走 **HITL**（`propose_persist` + 15min `confirm_token`）。

4、多轮对话与记忆：Mongo/内存 **Session** 持久化 `artifacts`；插单 **need_input** 中断后基于 `insert_job_intake` + `MemoryManager` 续聊补全工艺；前端 `AgentChatPanel` 绑定计划工单上下文，交期/方案对比/齐套结果 **卡片化展示**。

**效果评测：**

1、搭建 **L2/L3 分层自动化评测**（65 条话术 1:1 对齐）：L2 Preview（路由+Plan+Parse）通过率 **87.3%**（55/63）；L3 端到端 Exec 核心冒烟 **87.5%**（14/16）；**异常重排 Agent L3 全量 14/14**；events/plans/对抗路由 L2 均为 **100%**。

2、建立 **规则 + GLM** 双轨验收：`test_router_phrases.py` **20/20** 条车间话术命中预期 Agent；`glm_smoke` **21** 条 + Agent E2E **pytest 70+** 回归；编排器 **GLM 关闭可 rule_fallback** 降级排产。

3、架构上 **LLM 不直接算甘特**：排程/重排/物料在 Tool 完成，结果可复现；详见 [`agent-effectiveness-evaluation.md`](agent-effectiveness-evaluation.md)。

---

## 版本二（投递后端 / 全栈 / 制造信息化）

**制造 APS + Multi-Agent 排产调度平台**  
**2025/06 – 2026/05**

**技术栈：** Python、FastAPI、Uvicorn、Motor、MongoDB、Vue3、Vite、Element Plus、Pinia、ECharts、JSSP、PyTorch（DQN/PPO 等求解器）、元启发/强化学习求解器、REST、SSE、6 路 `/api/agents` 接口

**项目背景：** 基于 Job Shop Scheduling 的车间级 APS 与生产执行产品，支持计划库工单管理、多算法排程对比、看板仿真与异常重排；后接入 **Multi-Agent 自然语言编排**，形成 **REST 看板 + Agent 对话双入口** 共用同一重排与持久化内核。

**工作内容：**

1、搭建 **FastAPI** 统一后端（`tests/main.py`），暴露 `/api/run` 多算法排程、**8 类** `POST /api/events/*_reschedule`、`/api/execution/state` 执行态、计划库 CRUD、**6 个** `/api/agents/{id}/run` 及编排器接口；MongoDB 存储 `work_orders`、会话与 HITL 待确认队列。

2、排程引擎产品化：`solver_registry` 注册 **14** 种算法（SPT/TS/GA/SA/ACO/DQN/PPO 等），`compare_solvers` 输出 makespan、拖期、能耗等多指标；APS 支持策略权重、停机窗口、异步长任务与甘特/瓶颈报表。

3、生产异常三场景重排：`production_execution` 维护 `baseline_gantt` 与仿真时钟；故障等事件生成 **R1 时间推演** + **R2 冻结残段重排**；影响评估写回计划库与执行态，前端 `ImpactDualGantt` / `impactReport` 统一解包多层 `impact_summary`。

4、Vue3 单页应用（`/new-ui`）：排程中心、生产看板、分析报表、物料库存、智能助手；`PersistConfirmDialog` 覆盖式落库确认；构建产物单端口 **8008** 部署。

**效果评测：**

1、核心模块 pytest 覆盖：计划 BSON 序列化、HITL 落库、设备故障 R0/R1/R2、编排 Session 续跑、物料 BOM 等；与助手共用的 `event_reschedule` 保证看板按钮与对话重排 **行为一致**。

2、计划库 + 执行态 + 排程快照一体化后，异常重排结果可回写甘特并在分析页对比「重排前/传播/重排后」，支撑车间异常决策演示（本地算例下单次 `scheduling.run` 约 **百毫秒级**，视工单规模与算法数量浮动）。

---

## 可直接粘贴的合并版（仅 Agent 岗，一段式）

**Multi-Agent 制造排程智能体系统 | 2025/10 – 2026/05**  
技术栈：Python、FastAPI、智谱 GLM、自研 Agent 编排（LlmNode 链 + Plan-and-Solve + Tool 白名单）、SSE、MongoDB、Vue3、pytest  
项目背景：面向车间 JSSP 排产与生产异常调度，针对口语难用、意图混杂、重排与落库割裂等问题，搭建【路由—规划—Tool 执行—HITL 落库】Multi-Agent 链路，在 6 类意图、30 个 Tool、20 条标准话术上完成自动化验收。  
工作内容：① 设计 6 专责 Agent + SSE 编排器（Route/Plan/Execute/Summarize），GLM 优先并配规则 Guard/回退。② 实现 30 个 Tool，对接 14 求解器、8 类异常事件与 R0/R1/R2 影响评估，排程落库 HITL 确认。③ 会话 Memory + 插单多轮补全；前端助手展示思考轨迹与交期/方案对比卡片。  
效果评测：L2 自动化 65 条话术通过率 87%；L3 端到端核心场景 87.5%，异常重排 L3 全量 14/14；20 条规则路由 100% 命中；70+ pytest + GLM 冒烟回归；LLM 关闭可规则降级，甘特由确定性引擎计算。

---

## 与 SU7 RAG 项目并列时的写法提示

| 维度 | SU7 手册 RAG | Multi-Agent 制造排程 |
|------|----------------|----------------------|
| 领域 | 文档问答、检索增强 | 制造排程、Multi-Agent、Tool 编排 |
| 模型 | Qwen LoRA + Rerank | 智谱 GLM（`requests` 直调）+ 自研 LlmNode 链，非 LangGraph |
| 评测 | RAGas 语义分、延迟压测 | 路由命中率、pytest、三场景甘特 |
| 亮点词 | 混合检索、蒸馏 SFT | Plan-and-Solve、HITL、R0/R1/R2 |

两项目可同时体现：**端到端 LLM 应用搭建**（RAG）+ **Multi-Agent 与领域 Tool**（制造排程），避免重复堆砌「调用 GLM」而无差异。

---

## 项目命名备选（简历标题，均含 Agent / Multi-Agent）

| 优先级 | 项目名 | 说明 |
|--------|--------|------|
| ★ 主推 | **Multi-Agent 制造排程智能体系统** | Agent 岗最贴切；中英文关键词都有 |
| 备选 1 | **车间 Multi-Agent 排产与异常调度系统** | 突出口语排产 + 8 类异常重排 |
| 备选 2 | **制造排程 Multi-Agent 编排平台** | 强调编排器、Plan-and-Solve |
| 备选 3 | **离散制造 Multi-Agent 生产调度 Agent 平台** | 「Agent」出现两次，略长，投递 Agent 岗可用 |
| 全栈副标题 | **制造 APS + Multi-Agent 排产调度平台** | 版本二已采用；兼顾 APS 与 Agent |
| 英文简历 | **Shop-Floor Multi-Agent Scheduling Copilot** | 外企/英文 CV 一行标题 |

**写法技巧：** 主标题用上表之一；若版面紧，副标题补一句：`6 专责 Agent · 智谱 GLM · Plan-and-Solve · 30 Tools`。

---

## Agent / 大模型技术栈（与代码一致，面试可照此说）

| 类别 | 本项目实际用法 | 简历勿写（未接入） |
|------|----------------|-------------------|
| 大模型 | 智谱 **GLM**（`glm-4.5-air` 等），`ZHIPU_API_KEY` + OpenAI 兼容 `/chat/completions` | vLLM、本地 Qwen 微调 |
| 编排框架 | **自研** `orchestrator`：`Route → Plan → Parse → Execute → Summarize`；`llm/chain.py` 的 **`LlmNode` 注册表**（注释对标 LangGraph 节点，**依赖里无 langgraph/langchain**） | LangGraph、LangChain、AutoGen |
| 范式 | **Plan-and-Solve**（GLM 出 Tool 步骤）+ 确定性 Tool 执行；可选 **ReAct / Reflect** 节点 | 纯 ReAct 端到端算甘特 |
| Tool | `metaforge.tools` 白名单注册 ~30 个，Agent `allowed_tools` 约束 | MCP 生产级（仅 Phase6 骨架，默认关） |
| 流式 | `POST /api/orchestrator/stream` **SSE** | WebSocket |
| 记忆 | Mongo/内存 **Session**、`artifacts`、插单 `insert_job_intake` 续聊 | 向量库 RAG |
| 护栏 | 规则 Guard + `rule_fallback`（GLM 超时/关闭） | 全靠 prompt |
| 后端 | FastAPI、Pydantic（`tests/main.py` API 模型）、pytest | Linux/Docker 非必需 |

开发环境为 **Windows**；部署为本地 `uvicorn` + 可选 Mongo，无 Docker 镜像要求。

## 使用说明

1. 时间：Git 首提约 2025-06，多智能体集中 2025-10 后；请按真实实习/项目周期改。  
2. 效果评测推荐写 **L2 87% / L3 冒烟 87.5% / events L3 14/14**；勿写未复测的全量 L3 62%（含 skip 与 harness 问题，见效果评测报告）。  
3. 若 HR 问「为什么不用 LangGraph」：业务 Tool 需确定性 + 车间可复现，采用 **自研节点链 + 白名单 Tool**，与 LangGraph 的图编排思想类似但未引入其运行时。  
4. 详细技术索引仍见 [`智能体功能清单.md`](智能体功能清单.md)。
