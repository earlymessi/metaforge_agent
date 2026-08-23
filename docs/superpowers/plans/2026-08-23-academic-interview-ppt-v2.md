# MetaForge Agent 面试 PPT 学术版改版实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将现有 MetaForge Agent 面试 PPT 改为流程图主导、低饱和浅色、技术标题严谨的学术汇报版本。

**架构：** 保留 11 页内容和逐页备注，沿用 `@oai/artifact-tool` 的可编辑对象生成流程。通过统一页眉、平面分区、细线连接器和单一强调色重构页面，再用 WPS COM 打开与另存验证兼容性。

**技术栈：** JavaScript ES Modules、`@oai/artifact-tool`、WPS Office COM、PowerShell、演示文稿渲染与溢出检测工具。

---

### 任务 1：建立改版工作区与源文件基线

**文件：**
- 读取：`deliverables/MetaForge_Agent_Interview_Academic_Light.pptx`
- 修改：`.tmp/metaforge_agent_ppt_20260823/build_deck.mjs`
- 创建：`.tmp/metaforge_agent_ppt_v2_20260823/template-audit.txt`
- 创建：`.tmp/metaforge_agent_ppt_v2_20260823/template-frame-map.json`

- [ ] **步骤 1：加载工作区依赖并建立 V2 临时目录**

运行 `codex_app__load_workspace_dependencies`，记录 `RUNTIME_NODE`、`RUNTIME_NODE_MODULES` 和 `RUNTIME_BIN_DIR`，建立 V2 工作目录和 Node 模块 junction。

- [ ] **步骤 2：检查原 11 页渲染结果和标题**

运行模板检查脚本并核对每页 PNG、布局 JSON、字体和备注，记录现有页面的问题：宣传式标题、彩色卡片、流程图不足。

- [ ] **步骤 3：建立输出映射**

在 `template-frame-map.json` 中按 1→1、2→2 至 11→11 映射全部页面，记录每页的标题、主图和保留内容。

### 任务 2：重构全局视觉系统

**文件：**
- 修改：`.tmp/metaforge_agent_ppt_20260823/build_deck.mjs`

- [ ] **步骤 1：修改颜色和页眉函数**

将背景、正文、辅助线和强调色收敛为深蓝、灰白、橙色和必要的低饱和绿色；页标题改为 40–44 px 的技术主题名，删除宣传式 claim 标题结构。

- [ ] **步骤 2：修改通用图示组件**

增加流程节点、分组容器、泳道、直角连接器、步骤编号和图例函数；连接器先于节点创建，确保箭头位于节点之后且不穿过文字。

### 任务 3：重构 7 页主讲内容

**文件：**
- 修改：`.tmp/metaforge_agent_ppt_20260823/build_deck.mjs`

- [ ] **步骤 1：重构封面与两层架构页**

封面加入四段技术闭环；第 2 页绘制 Router、业务 Agent、Scheduling Supervisor、域内 Agent 和 Tool/Solver/Memory 的层级架构。

- [ ] **步骤 2：重构任务编排与 Tool 页**

第 3 页绘制 Preview/HITL/Run 时序与设备故障任务链；第 4 页绘制 JSON Plan 到 Solver 的 Tool Contract 执行链。

- [ ] **步骤 3：重构上下文、重调度与代码页**

第 5 页绘制三类 Memory 经 Context Compiler 的数据流；第 6 页绘制故障重调度状态流与评测表；第 7 页保留真实代码并增加 Parse、Execute、Persist 一致性关系图。

### 任务 4：重构 4 页备份内容

**文件：**
- 修改：`.tmp/metaforge_agent_ppt_20260823/build_deck.mjs`

- [ ] **步骤 1：职责和能力接入**

第 8 页使用职责矩阵，第 9 页使用 Tool 注册和 Solver/Event 接入图，删除三栏彩色卡片。

- [ ] **步骤 2：稳定性和评测**

第 10 页使用 Router、Plan、Tool、Agent、Solver、Persist 异常泳道；第 11 页使用分层评测表和口径说明。

### 任务 5：生成和质量验证

**文件：**
- 创建：`deliverables/MetaForge_Agent_Interview_Academic_Flow_v2.pptx`
- 创建：`.tmp/metaforge_agent_ppt_v2_20260823/slide-*.png`
- 创建：`.tmp/metaforge_agent_ppt_v2_20260823/slide-*.layout.json`

- [ ] **步骤 1：标记并执行编辑操作**

运行 `mark_artifact_operation_started.mjs --operation-kind edit --expected-output-count 1 --output-format pptx`，随后使用绑定的 Node 运行构建脚本。

- [ ] **步骤 2：逐页渲染和目视检查**

渲染 11 页 PPTX，逐页检查标题、流程箭头、文字换行、颜色数量、备注和页码；发现问题后修改构建脚本并重新生成。

- [ ] **步骤 3：运行溢出检测**

运行 `slides_test.py deliverables/MetaForge_Agent_Interview_Academic_Flow_v2.pptx`，预期输出 `Test passed. No overflow detected.`。

- [ ] **步骤 4：运行 WPS 兼容性检查**

使用 WPS Office 12.0 COM 打开 V2，确认 11 页及图形对象可读取，另存为 OOXML `.pptx` 后再次渲染和运行溢出检测。

