# MetaForge 文档索引

> 更新：2026-05-31

## 现行文档（请以这些为准）

| 文档 | 用途 |
|------|------|
| [智能体功能清单.md](智能体功能清单.md) | **六大业务 Agent** 路由、Tool 链、API、示例话术（主参考） |
| [多智能体开发进度.md](多智能体开发进度.md) | 实现状态、Phase 完成情况、测试命令 |
| [改进计划.md](改进计划.md) | 产品路线图与里程碑 |
| [技术报告.md](技术报告.md) | 系统技术说明（软著/汇报用） |
| [简历-项目经历-MetaForge.md](简历-项目经历-MetaForge.md) | 简历用项目经历（Agent 版 / 工程版双版本） |
| [plans-e2e-test-outline.md](plans-e2e-test-outline.md) | 计划库 × 排程链路手工测试大纲 |
| [agent-glm-e2e-test-plan.md](agent-glm-e2e-test-plan.md) | **Agent GLM 联调 + 端到端执行** 自动化评测方案（L2/L3） |
| [agent-effectiveness-evaluation.md](agent-effectiveness-evaluation.md) | **Agent 效果评测报告**（基于 L2/L3 自动化报告，软著/汇报用） |

## 其他

| 文档 | 用途 |
|------|------|
| [usage.md](usage.md) | 使用说明 |
| [development.md](development.md) | 开发环境 |
| [solvers.md](solvers.md) | 求解器概览 |
| [datasets.md](datasets.md) | 算例格式 |

## 历史归档

已完成的分步实施计划与设计初稿见 **[archive/](archive/README.md)**，勿与现行行为混用。

### 关键变更（2026-05-31）

- 业务 Agent 为 **6 个**：`scheduling`、`events`、`kitting`、`commitment`、`whatif`、`plans`
- 原第 7 个 **`pipeline` 已合并入 `scheduling`**（排程 + HITL 落库）
- 兼容：`POST /api/agents/pipeline/run`、`intent=pipeline` → 仍指向 scheduling
