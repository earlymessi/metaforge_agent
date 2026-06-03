# 计划库 × 智能排程 — 链路测试大纲

> 文档索引：[`README.md`](README.md) · Agent 路由验收：`tests/test_router_phrases.py`（20 条话术）

> **统一端口：8008** — 访问 http://127.0.0.1:8008/new-ui/ ，启动：`.\scripts\restart_backend.ps1`
> 单元测试：`pytest tests/test_orchestrator_router.py tests/test_plan_store_bson.py tests/test_agents_plans.py tests/test_plans_intent_extended.py` → 21 passed

## A. 环境与后端
- A1 后端可达（8008 优先）
- A2 `/api/llm/status` 含 `router_build_id`（新代码）
- A3 MongoDB 计划列表 API `/api/db/list`

## B. 意图路由（Orchestrator）
- B1 「新建计划b」→ `plans` agent（非 scheduling）
- B2 `route-debug` 返回 `router: rule` 或正确 intent

## C. 计划 CRUD（Tool / API）
- C1 `data.create_plan` 创建空计划（无 JobData BSON 错误）
- C2 计划出现在 `/api/db/list`
- C3 `PUT /api/db/update/{id}` 更新名称与工单
- C4 `GET` 单计划 jobs 与名称一致

## D. 对话 → 前端上下文
- D1 `active_plan` 含 plan_id、plan_name、jobs=[]
- D2 `ui_action` navigate `/aps`

## E. APS 工单池（需浏览器；本脚本测 localStorage 契约）
- E1 `aps_load_force_custom` + 空 jobs 应触发自定义模式
- E2 计划名写入 `aps_load_plan_name`

## F. 回归
- F1 `test_orchestrator_router` 计划库路由
- F2 `test_plan_store_bson` Pydantic 序列化
- F3 `test_agents_plans` Agent 步骤
