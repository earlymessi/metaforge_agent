import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const ROOT = "D:/Desktop/metaforge";
const TMP = `${ROOT}/.tmp/metaforge_agent_ppt_20260823`;
const FINAL = `${ROOT}/deliverables/MetaForge_Agent_Interview_Academic_Light.pptx`;

const W = 1280;
const H = 720;
const FONT = "Microsoft YaHei";
const MONO = "Consolas";
const C = {
  primary: "#1A3C8B",
  primaryDark: "#143064",
  primaryPale: "#E8EEF9",
  secondary: "#E67733",
  secondaryPale: "#FDF1E8",
  accent: "#188050",
  accentPale: "#E8F4EE",
  text: "#222222",
  muted: "#64748B",
  light: "#F5F8FC",
  line: "#D6E0EE",
  white: "#FFFFFF",
  danger: "#B6473A",
  dangerPale: "#FBEDEC",
};

function addShape(slide, geometry, pos, fill = C.white, lineFill = "none", lineWidth = 0, name) {
  return slide.shapes.add({
    geometry,
    name,
    position: pos,
    fill,
    line: { style: "solid", fill: lineFill, width: lineWidth },
  });
}

function addText(slide, text, pos, opts = {}) {
  const box = slide.shapes.add({
    geometry: "textbox",
    name: opts.name,
    position: pos,
    fill: opts.fill ?? "none",
    line: { style: "solid", fill: opts.lineFill ?? "none", width: opts.lineWidth ?? 0 },
  });
  box.text = text;
  box.text.style = {
    fontSize: opts.fontSize ?? 22,
    bold: opts.bold ?? false,
    color: opts.color ?? C.text,
    alignment: opts.align ?? "left",
    verticalAlignment: opts.valign ?? "top",
    autoFit: opts.autoFit ?? "shrinkText",
    wrap: "square",
    typeface: opts.typeface ?? FONT,
    lineSpacing: opts.lineSpacing ?? 1.1,
    insets: opts.insets ?? { top: 4, right: 6, bottom: 4, left: 6 },
  };
  return box;
}

function addBulletList(slide, items, pos, opts = {}) {
  const box = addText(slide, "", pos, {
    fontSize: opts.fontSize ?? 22,
    color: opts.color ?? C.text,
    fill: opts.fill ?? "none",
    lineFill: opts.lineFill ?? "none",
    lineWidth: opts.lineWidth ?? 0,
    insets: opts.insets ?? { top: 8, right: 10, bottom: 8, left: 10 },
    name: opts.name,
  });
  box.text.set(items.map((item) => ({
    bulletCharacter: opts.bulletCharacter ?? "•",
    marginLeft: opts.marginLeft ?? 22,
    indent: opts.indent ?? -12,
    spaceAfter: opts.spaceAfter ?? 9,
    runs: Array.isArray(item) ? item : [item],
  })));
  box.text.style = {
    fontSize: opts.fontSize ?? 22,
    color: opts.color ?? C.text,
    typeface: FONT,
    lineSpacing: opts.lineSpacing ?? 1.08,
    autoFit: "shrinkText",
    wrap: "square",
    insets: opts.insets ?? { top: 8, right: 10, bottom: 8, left: 10 },
  };
  return box;
}

function addArrow(slide, pos, direction = "right", color = C.line) {
  const geometry = direction === "down" ? "downArrow" : "rightArrow";
  return addShape(slide, geometry, pos, color, "none", 0);
}

function addHeader(slide, section, claim, page, backup = false) {
  addShape(slide, "rect", { left: 0, top: 0, width: W, height: 10 }, C.primary);
  addText(slide, backup ? "BACKUP" : section, { left: 72, top: 28, width: 230, height: 28 }, {
    fontSize: 16, bold: true, color: backup ? C.secondary : C.primary, valign: "middle",
  });
  addText(slide, claim, { left: 72, top: 63, width: 1110, height: 64 }, {
    fontSize: 47, bold: true, color: C.primaryDark, valign: "middle", lineSpacing: 0.95,
  });
  addText(slide, String(page).padStart(2, "0"), { left: 1180, top: 34, width: 42, height: 24 }, {
    fontSize: 14, bold: true, color: C.muted, align: "right",
  });
  addShape(slide, "rect", { left: 72, top: 137, width: 1136, height: 2 }, C.line);
}

function addFooter(slide, text = "MetaForge · Agent 开发项目介绍") {
  addText(slide, text, { left: 72, top: 681, width: 520, height: 22 }, {
    fontSize: 13, color: C.muted, valign: "middle",
  });
}

function addTag(slide, text, pos, fill = C.primaryPale, color = C.primary) {
  const s = addShape(slide, "roundRect", pos, fill, "none", 0);
  s.text = text;
  s.text.style = {
    fontSize: 16, bold: true, color, alignment: "center", verticalAlignment: "middle",
    typeface: FONT, autoFit: "shrinkText", insets: { top: 2, right: 6, bottom: 2, left: 6 },
  };
  return s;
}

function addStat(slide, value, label, pos, color = C.primary, pale = C.primaryPale) {
  addShape(slide, "roundRect", pos, pale, color, 1);
  addText(slide, value, { left: pos.left + 14, top: pos.top + 10, width: pos.width - 28, height: 60 }, {
    fontSize: 44, bold: true, color, align: "center", valign: "middle",
  });
  addText(slide, label, { left: pos.left + 14, top: pos.top + 70, width: pos.width - 28, height: pos.height - 78 }, {
    fontSize: 17, color: C.text, align: "center", valign: "middle",
  });
}

function addNode(slide, text, pos, opts = {}) {
  const s = addShape(slide, "roundRect", pos, opts.fill ?? C.white, opts.line ?? C.line, opts.lineWidth ?? 1);
  s.text = text;
  s.text.style = {
    fontSize: opts.fontSize ?? 19,
    bold: opts.bold ?? true,
    color: opts.color ?? C.text,
    alignment: "center",
    verticalAlignment: "middle",
    autoFit: "shrinkText",
    typeface: FONT,
    insets: { top: 6, right: 8, bottom: 6, left: 8 },
  };
  return s;
}

function addNotes(slide, talk, sources) {
  const notes = `${talk}\n\n[Sources]\n${sources.map((s) => `- ${s}`).join("\n")}`;
  slide.speakerNotes.textFrame.setText(notes);
  slide.speakerNotes.setVisible(true);
}

function styleTable(table, rows, cols, opts = {}) {
  table.borders.assign({ style: "solid", fill: C.line, width: 1 });
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const cell = table.getCell(r, c);
      cell.fill = r === 0 ? C.primary : (r % 2 === 0 ? C.light : C.white);
      cell.text.style = {
        fontSize: r === 0 ? (opts.headerFontSize ?? 18) : (opts.fontSize ?? 17),
        bold: r === 0,
        color: r === 0 ? C.white : C.text,
        typeface: FONT,
        alignment: c === 0 ? "left" : "center",
        verticalAlignment: "middle",
        autoFit: "shrinkText",
        insets: { top: 4, right: 6, bottom: 4, left: 6 },
      };
    }
  }
}

async function main() {
  await fs.mkdir(TMP, { recursive: true });
  await fs.mkdir(path.dirname(FINAL), { recursive: true });
  const presentation = Presentation.create({ slideSize: { width: W, height: H } });

  // Slide 1 — cover + problem tension
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addShape(slide, "rect", { left: 0, top: 0, width: 14, height: H }, C.primary);
    addShape(slide, "rect", { left: 860, top: 0, width: 420, height: H }, C.primary);
    addText(slide, "国家重点研发项目 · Agent 开发项目介绍", { left: 72, top: 72, width: 610, height: 30 }, {
      fontSize: 17, bold: true, color: C.primary,
    });
    addText(slide, "Multi-Agent\n制造排程智能体系统", { left: 72, top: 138, width: 715, height: 190 }, {
      fontSize: 68, bold: true, color: C.primaryDark, lineSpacing: 0.92,
    });
    addText(slide, "LLM 做决策编排，Solver 做确定性排程", { left: 78, top: 348, width: 650, height: 42 }, {
      fontSize: 28, color: C.secondary, bold: true,
    });
    addText(slide, "Python · Multi-Agent · Agent Harness · Memory · FastAPI · MongoDB", { left: 78, top: 425, width: 720, height: 54 }, {
      fontSize: 19, color: C.muted,
    });
    addTag(slide, "2025.04—2025.12", { left: 78, top: 510, width: 210, height: 34 }, C.light, C.primary);
    addTag(slide, "面向离散制造排程与异常重调度", { left: 304, top: 510, width: 330, height: 34 }, C.accentPale, C.accent);

    addText(slide, "真实问题", { left: 906, top: 86, width: 270, height: 32 }, {
      fontSize: 20, bold: true, color: C.white,
    });
    addShape(slide, "roundRect", { left: 900, top: 140, width: 300, height: 164 }, C.white, C.white, 1);
    addText(slide, "“3 号机坏了 4 小时，\n哪些订单会延期？\n给我影响最小的重排方案。”", { left: 920, top: 166, width: 260, height: 112 }, {
      fontSize: 23, bold: true, color: C.primaryDark, align: "center", valign: "middle", lineSpacing: 1.12,
    });
    addText(slide, "业务语言", { left: 900, top: 342, width: 90, height: 28 }, {
      fontSize: 16, bold: true, color: C.white, align: "center",
    });
    addArrow(slide, { left: 998, top: 347, width: 46, height: 20 }, "right", C.secondary);
    addText(slide, "执行链", { left: 1052, top: 342, width: 80, height: 28 }, {
      fontSize: 16, bold: true, color: C.white, align: "center",
    });
    const ganttY = 410;
    const gantt = [
      [0, 72, C.secondary], [82, 116, C.accent], [210, 54, C.white],
      [24, 92, C.accent], [130, 100, C.secondary], [242, 44, C.white],
      [0, 50, C.white], [62, 140, C.secondary], [214, 74, C.accent],
    ];
    gantt.forEach((g, i) => {
      const row = Math.floor(i / 3);
      addShape(slide, "roundRect", { left: 900 + g[0], top: ganttY + row * 48, width: g[1], height: 22 }, g[2], "none", 0);
    });
    addText(slide, "意图判断 · 参数补全 · 策略选择 · 结果解释 · 人工确认", { left: 895, top: 583, width: 310, height: 72 }, {
      fontSize: 17, color: C.white, align: "center", valign: "middle",
    });
    addNotes(slide,
      "这个项目面向离散制造车间排程。传统 APS 能运行算法，但业务人员通常只会说“交付优先排一下”或“3 号机坏了，帮我重排”。我引入 Agent 作为决策编排层：负责识别意图、补齐信息、选择业务能力、组织执行顺序和解释结果；真正的甘特图仍由确定性求解器生成。",
      [`${ROOT}/docs/求职面试-PPT素材-MetaForge-Agent.md`, `${ROOT}/README.md`]);
  }

  // Slide 2 — two-layer architecture
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "系统架构", "业务分诊与域内协作分成两层", 2);
    addText(slide, "L1 · 六岗业务分诊（单请求只选一个 Agent）", { left: 72, top: 154, width: 620, height: 30 }, {
      fontSize: 20, bold: true, color: C.primary,
    });
    addArrow(slide, { left: 610, top: 190, width: 52, height: 24 }, "right", C.secondary);
    addNode(slide, "用户 / APS", { left: 72, top: 186, width: 160, height: 58 }, { fill: C.light, line: C.line, color: C.primaryDark });
    addNode(slide, "Router\nGLM + Guard", { left: 266, top: 180, width: 210, height: 70 }, { fill: C.primary, line: C.primary, color: C.white, fontSize: 20 });
    addArrow(slide, { left: 493, top: 199, width: 64, height: 22 }, "right", C.primaryPale);

    const agents = [
      ["排程", C.primary, C.white], ["异常", C.secondaryPale, C.secondary], ["齐套", C.accentPale, C.accent],
      ["交期", C.primaryPale, C.primary], ["What-if", C.light, C.primaryDark], ["计划管理", C.light, C.primaryDark],
    ];
    const startX = 568;
    agents.forEach((a, i) => addNode(slide, a[0], { left: startX + i * 105, top: 186, width: 92, height: 58 }, {
      fill: a[1], line: i === 0 ? C.primary : C.line, color: a[2], fontSize: 17,
    }));

    addText(slide, "L2 · 仅 Scheduling 进入 Supervisor 协作", { left: 72, top: 292, width: 600, height: 30 }, {
      fontSize: 20, bold: true, color: C.primary,
    });
    addArrow(slide, { left: 620, top: 345, width: 46, height: 22 }, "right", C.secondary);
    addArrow(slide, { left: 782, top: 345, width: 46, height: 22 }, "right", C.secondary);
    addArrow(slide, { left: 938, top: 345, width: 46, height: 22 }, "right", C.secondary);
    addShape(slide, "roundRect", { left: 72, top: 330, width: 930, height: 228 }, C.light, C.line, 1);
    addNode(slide, "Planning\nSupervisor", { left: 100, top: 365, width: 160, height: 86 }, { fill: C.primary, line: C.primary, color: C.white, fontSize: 20 });
    addNode(slide, "Order\n订单风险", { left: 315, top: 347, width: 135, height: 72 }, { fill: C.white, line: C.primary, color: C.primary });
    addNode(slide, "Constraint\n硬/软约束", { left: 473, top: 347, width: 135, height: 72 }, { fill: C.white, line: C.primary, color: C.primary });
    addNode(slide, "Resource\n瓶颈负载", { left: 631, top: 347, width: 135, height: 72 }, { fill: C.white, line: C.primary, color: C.primary });
    addNode(slide, "artifacts\n任务状态", { left: 796, top: 347, width: 130, height: 72 }, { fill: C.accentPale, line: C.accent, color: C.accent });
    addNode(slide, "Strategy → HITL → Solver → Eval", { left: 315, top: 460, width: 611, height: 60 }, { fill: C.primaryPale, line: C.primary, color: C.primaryDark, fontSize: 20 });
    addText(slide, "Agent 不自由群聊；依赖关系显式写在 Supervisor 中", { left: 100, top: 484, width: 190, height: 54 }, {
      fontSize: 16, color: C.muted, align: "center", valign: "middle",
    });

    addShape(slide, "roundRect", { left: 1032, top: 330, width: 176, height: 228 }, C.white, C.line, 1);
    addText(slide, "设计原则", { left: 1052, top: 348, width: 136, height: 34 }, {
      fontSize: 22, bold: true, color: C.secondary, align: "center",
    });
    addBulletList(slide, ["六岗互斥路由", "内层按需协作", "统一协议交付", "Supervisor 不算甘特"], { left: 1044, top: 396, width: 150, height: 138 }, {
      fontSize: 17, spaceAfter: 7,
    });
    addFooter(slide);
    addNotes(slide,
      "我没有把系统设计成六个 Agent 自由群聊，而是采用两层架构。外层 Router 只选择一个业务 Agent，控制工具范围和错误影响面。只有智能排程进入内层 Supervisor：Order 先分析订单，Constraint 使用订单结果，Resource 可并行，最后通过 artifacts 合并到策略、求解和评价流水线。",
      [`${ROOT}/src/metaforge/agents/registry_meta.py`, `${ROOT}/src/metaforge/orchestrator/router.py`, `${ROOT}/src/metaforge/planning_collab/supervisor.py`, `${ROOT}/src/metaforge/planning_collab/protocol.py`]);
  }

  // Slide 3 — Plan and Solve
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "任务编排", "先规划、再执行，每一步都可预览", 3);
    const steps = [
      ["01", "Route", "识别唯一业务域"], ["02", "Plan", "生成 Tool 步骤"], ["03", "Parse", "结构化业务参数"],
      ["04", "Execute", "确定性执行"], ["05", "Summarize", "解释结果"],
    ];
    for (let i = 0; i < 4; i += 1) addArrow(slide, { left: 260 + i * 235, top: 206, width: 48, height: 22 }, "right", i === 3 ? C.accent : C.secondary);
    steps.forEach((s, i) => {
      const x = 72 + i * 235;
      addShape(slide, "roundRect", { left: x, top: 170, width: 190, height: 96 }, i === 3 ? C.accentPale : C.primaryPale, i === 3 ? C.accent : C.primary, 1);
      addText(slide, s[0], { left: x + 12, top: 180, width: 38, height: 28 }, { fontSize: 14, bold: true, color: i === 3 ? C.accent : C.primary });
      addText(slide, s[1], { left: x + 50, top: 178, width: 126, height: 32 }, { fontSize: 22, bold: true, color: C.primaryDark });
      addText(slide, s[2], { left: x + 16, top: 218, width: 158, height: 36 }, { fontSize: 16, color: C.muted, align: "center", valign: "middle" });
    });

    addShape(slide, "roundRect", { left: 72, top: 306, width: 730, height: 318 }, C.light, C.line, 1);
    addText(slide, "示例：3 号机坏了 4 小时，按当前进度重排", { left: 96, top: 326, width: 680, height: 36 }, {
      fontSize: 23, bold: true, color: C.primaryDark,
    });
    const tools = [
      ["execution.get_state", "读取仿真时钟与原计划"],
      ["events.parse_event", "解析 machine / start / duration"],
      ["events.check_insert_job", "统一事件校验"],
      ["events.reschedule", "生成 R0 / R1 / R2"],
      ["delivery.compare_commitment", "比较交期变化"],
      ["delivery.explain_impact", "形成业务解释"],
    ];
    tools.forEach((t, i) => {
      const y = 378 + i * 37;
      addTag(slide, String(i + 1).padStart(2, "0"), { left: 96, top: y, width: 42, height: 26 }, i === 3 ? C.accentPale : C.primaryPale, i === 3 ? C.accent : C.primary);
      addText(slide, t[0], { left: 150, top: y - 1, width: 292, height: 28 }, { fontSize: 17, bold: true, color: C.primaryDark, typeface: MONO });
      addText(slide, t[1], { left: 456, top: y - 1, width: 310, height: 28 }, { fontSize: 17, color: C.muted });
    });

    addShape(slide, "roundRect", { left: 834, top: 306, width: 374, height: 318 }, C.white, C.line, 1);
    addText(slide, "关键路径不完全自由规划", { left: 858, top: 330, width: 326, height: 40 }, {
      fontSize: 24, bold: true, color: C.secondary, align: "center",
    });
    addBulletList(slide, [
      ["开放需求：", { run: "LLM Plan + 白名单", textStyle: { bold: true, color: C.primary } }],
      ["关键流程：", { run: "Supervisor / 固定阶段", textStyle: { bold: true, color: C.accent } }],
      ["Plan 失败：", { run: "rule_fallback", textStyle: { bold: true, color: C.secondary } }],
      ["Preview：", { run: "不执行副作用", textStyle: { bold: true, color: C.primary } }],
      ["Run：", { run: "复用 cached_plan_steps", textStyle: { bold: true, color: C.primary } }],
    ], { left: 858, top: 390, width: 326, height: 190 }, { fontSize: 19, spaceAfter: 12 });
    addFooter(slide);
    addNotes(slide,
      "主路径采用 Plan-and-Solve。Preview 阶段只返回 Route、Plan 和 Parse，不执行副作用；确认后 Harness 再执行 Tool。开放需求可以由 LLM 生成计划，但排程协作和异常重排使用 Supervisor 或固定阶段流水线。Preview 生成的 Plan 会缓存到上下文，Run 阶段直接复用。",
      [`${ROOT}/src/metaforge/orchestrator/preview.py`, `${ROOT}/src/metaforge/orchestrator/llm/chain.py`, `${ROOT}/src/metaforge/events_collab/plan_steps.py`, `${ROOT}/src/metaforge/events_collab/pipeline.py`]);
  }

  // Slide 4 — Tool Contract
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "工具治理", "Tool Contract 隔离模型与制造计算", 4);
    addText(slide, "结构化 Function Calling 执行链", { left: 72, top: 158, width: 590, height: 34 }, {
      fontSize: 22, bold: true, color: C.primary,
    });
    const stages = [
      ["JSON Plan", "模型只生成结构化意图", C.primaryPale, C.primary],
      ["allowed_tools", "Agent 白名单校验", C.primaryPale, C.primary],
      ["Policy Gate", "allow / ask / deny", C.secondaryPale, C.secondary],
      ["Schema", "输入与输出契约", C.accentPale, C.accent],
      ["Execute", "timeout / retry / RunEvent", C.light, C.primaryDark],
    ];
    for (let i = 0; i < 4; i += 1) addArrow(slide, { left: 362, top: 247 + i * 78, width: 34, height: 20 }, "down", C.line);
    stages.forEach((s, i) => {
      const y = 202 + i * 78;
      addShape(slide, "roundRect", { left: 72, top: y, width: 560, height: 60 }, s[2], s[3], 1);
      addText(slide, s[0], { left: 94, top: y + 8, width: 180, height: 42 }, { fontSize: 20, bold: true, color: s[3], valign: "middle", typeface: i < 2 ? MONO : FONT });
      addText(slide, s[1], { left: 286, top: y + 8, width: 322, height: 42 }, { fontSize: 18, color: C.text, valign: "middle" });
    });

    addStat(slide, "30 → 34", "项目阶段 Tool → 当前注册数", { left: 684, top: 182, width: 236, height: 130 }, C.primary, C.primaryPale);
    addStat(slide, "6 × 14", "策略模板 × 求解器", { left: 944, top: 182, width: 236, height: 130 }, C.secondary, C.secondaryPale);
    addStat(slide, "8 类", "动态事件统一 event_envelope", { left: 684, top: 336, width: 236, height: 130 }, C.accent, C.accentPale);
    addStat(slide, "R0/R1/R2", "统一影响报告", { left: 944, top: 336, width: 236, height: 130 }, C.primaryDark, C.light);

    addShape(slide, "roundRect", { left: 684, top: 496, width: 496, height: 116 }, C.white, C.line, 1);
    addText(slide, "准确口径", { left: 704, top: 512, width: 100, height: 26 }, { fontSize: 17, bold: true, color: C.secondary });
    addText(slide, "模型客户端使用 JSON response_format；\nParser + 白名单 + ToolExecutor 实现 Function Calling 式调用。", { left: 704, top: 542, width: 456, height: 56 }, {
      fontSize: 18, color: C.text, valign: "middle",
    });
    addFooter(slide);
    addNotes(slide,
      "Tool 层是核心隔离层。项目阶段有 30 个 Tool，当前新增 4 个 planning Tool，共 34 个。模型输出 JSON Tool Plan，Parser 先做 Agent 白名单校验，ToolExecutor 再执行风险门禁、Schema、超时和重试。当前不是厂商原生 tools/tool_calls，而是自研的 Function Calling 式结构化执行链。",
      [`${ROOT}/src/metaforge/tools/base.py`, `${ROOT}/src/metaforge/tools/registry.py`, `${ROOT}/src/metaforge/harness/tool_executor.py`, `${ROOT}/src/metaforge/orchestrator/llm/parsers.py`, `${ROOT}/src/metaforge/utils/solver_registry.py`, `${ROOT}/src/metaforge/services/event_reschedule.py`]);
  }

  // Slide 5 — Context and reliability
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "上下文", "上下文边界比“记住更多”更重要", 5);
    addText(slide, "三层 Memory：状态与事实分离", { left: 72, top: 158, width: 520, height: 34 }, { fontSize: 22, bold: true, color: C.primary });
    const layers = [
      ["① Session", "session_id · artifacts · context · TTL 1h", C.primary, C.white],
      ["② Task State", "working · pending · PlanningTaskState", C.primaryPale, C.primaryDark],
      ["③ Business Facts", "plan · MES · gantt · jobs · inventory · Mongo", C.accentPale, C.accent],
    ];
    layers.forEach((l, i) => {
      const y = 204 + i * 130;
      addShape(slide, "roundRect", { left: 72, top: y, width: 544, height: 104 }, l[2], i === 0 ? C.primary : (i === 2 ? C.accent : C.line), 1);
      addText(slide, l[0], { left: 94, top: y + 14, width: 190, height: 34 }, { fontSize: 22, bold: true, color: l[3] });
      addText(slide, l[1], { left: 94, top: y + 52, width: 496, height: 36 }, { fontSize: 17, color: i === 0 ? C.white : C.text, valign: "middle", typeface: i === 2 ? MONO : FONT });
    });
    addText(slide, "Memory Boundary：禁止把甘特、工单、库存复制成第二个事实权威", { left: 72, top: 606, width: 544, height: 40 }, {
      fontSize: 16, bold: true, color: C.danger, align: "center", valign: "middle", fill: C.dangerPale, lineFill: C.danger, lineWidth: 1,
    });

    addText(slide, "Context Compiler 与稳定性", { left: 664, top: 158, width: 520, height: 34 }, { fontSize: 22, bold: true, color: C.primary });
    const reliabilities = [
      ["上下文裁剪", "目标 ≤ 500 字 · 订单摘要 ≤ 30 条 · 不传整张甘特", C.primaryPale, C.primary],
      ["一致性追踪", "稳定 context_hash · Preview 缓存 Plan · Run 复用", C.light, C.primaryDark],
      ["多轮续聊", "need_input / pending_clarification → 回到原 Agent", C.accentPale, C.accent],
      ["HITL", "策略 approve/edit/reject · 落库 token 15 min", C.secondaryPale, C.secondary],
      ["异常回退", "rule_fallback · Tool retry · human escalation", C.dangerPale, C.danger],
    ];
    reliabilities.forEach((r, i) => {
      const y = 204 + i * 83;
      addShape(slide, "roundRect", { left: 664, top: y, width: 544, height: 66 }, r[2], r[3], 1);
      addText(slide, r[0], { left: 684, top: y + 10, width: 126, height: 42 }, { fontSize: 19, bold: true, color: r[3], valign: "middle" });
      addText(slide, r[1], { left: 822, top: y + 8, width: 364, height: 46 }, { fontSize: 16, color: C.text, valign: "middle" });
    });
    addFooter(slide);
    addNotes(slide,
      "我把 Memory 分为 Session、Task State 和 Business Facts 三层。Session 管跨轮上下文，Task State 管当前任务与待补充信息，Mongo 与业务服务保存甘特、工单和库存等事实。Context Compiler 只保留高价值摘要并生成稳定 hash。策略和落库通过 HITL，模型或 Tool 失败时走规则回退、重试或人工升级。",
      [`${ROOT}/src/metaforge/orchestrator/session.py`, `${ROOT}/src/metaforge/memory/manager.py`, `${ROOT}/src/metaforge/memory/boundary.py`, `${ROOT}/src/metaforge/memory/pending.py`, `${ROOT}/src/metaforge/strategy/context_builder.py`, `${ROOT}/src/metaforge/services/persist_store.py`, `${ROOT}/src/metaforge/strategy/hitl.py`]);
  }

  // Slide 6 — scenario and metrics
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "场景评测", "R0 / R1 / R2 让重排效果可量化", 6);
    addShape(slide, "roundRect", { left: 72, top: 158, width: 714, height: 56 }, C.primaryPale, C.primary, 1);
    addText(slide, "设备故障 → 读取执行态 → 冻结已完成工序 → 残段重排 → HITL 落库", { left: 92, top: 168, width: 674, height: 36 }, {
      fontSize: 20, bold: true, color: C.primaryDark, align: "center", valign: "middle",
    });
    const scen = [
      ["R0 原计划", "基准甘特", C.primary, C.primaryPale],
      ["R1 不干预", "故障延迟传播", C.secondary, C.secondaryPale],
      ["R2 智能重排", "冻结 + 故障窗 + 残段求解", C.accent, C.accentPale],
    ];
    scen.forEach((s, i) => {
      const x = 72 + i * 238;
      addShape(slide, "roundRect", { left: x, top: 244, width: 218, height: 304 }, C.white, s[2], 1);
      addText(slide, s[0], { left: x + 14, top: 260, width: 190, height: 32 }, { fontSize: 22, bold: true, color: s[2], align: "center" });
      addText(slide, s[1], { left: x + 14, top: 296, width: 190, height: 28 }, { fontSize: 16, color: C.muted, align: "center" });
      for (let r = 0; r < 4; r += 1) {
        addText(slide, `M${r + 1}`, { left: x + 12, top: 346 + r * 42, width: 28, height: 20 }, { fontSize: 12, color: C.muted, align: "center" });
        addShape(slide, "rect", { left: x + 44, top: 354 + r * 42, width: 150, height: 2 }, C.line);
      }
      const bars = i === 0
        ? [[48,350,62],[115,392,54],[66,434,88],[135,476,50]]
        : i === 1
          ? [[48,350,62],[140,392,54],[92,434,88],[158,476,36]]
          : [[48,350,62],[110,392,62],[78,434,72],[126,476,58]];
      bars.forEach((b, j) => addShape(slide, "roundRect", { left: x + b[0], top: b[1], width: b[2], height: 18 }, j % 2 === 0 ? s[2] : C.primaryDark, "none", 0));
      addTag(slide, i === 0 ? "对照" : (i === 1 ? "自然传播" : "推荐"), { left: x + 59, top: 512, width: 100, height: 26 }, s[3], s[2]);
    });

    addText(slide, "分层评测", { left: 830, top: 158, width: 330, height: 34 }, { fontSize: 22, bold: true, color: C.primary });
    addStat(slide, "87.3%", "L2 Preview · 55 / 63", { left: 830, top: 206, width: 350, height: 116 }, C.primary, C.primaryPale);
    addStat(slide, "87.5%", "L3 核心冒烟 · 14 / 16", { left: 830, top: 338, width: 350, height: 116 }, C.secondary, C.secondaryPale);
    addStat(slide, "14 / 14", "Events L3 端到端", { left: 830, top: 470, width: 350, height: 116 }, C.accent, C.accentPale);
    addText(slide, "全量 L3 首轮：32 / 51（62.7%），另有 14 条跳过；不与核心冒烟混报。", { left: 830, top: 602, width: 350, height: 46 }, {
      fontSize: 15, color: C.muted, align: "center", valign: "middle",
    });
    addFooter(slide);
    addNotes(slide,
      "设备故障场景先读取当前仿真时钟和原计划，再生成三份结果：R0 是原计划，R1 模拟不干预时延迟如何传播，R2 冻结已完成工序并注入故障窗口后对剩余工序重排。评测上分为 Preview 和真实执行：L2 为 55/63，L3 核心冒烟为 14/16，异常重排 14/14。全量 L3 首轮 32/51，需要主动说明。",
      [`${ROOT}/src/metaforge/services/event_reschedule.py`, `${ROOT}/reports/agent_e2e_l2_20260601-114642.json`, `${ROOT}/reports/agent_e2e_l3_20260601-125055.json`, `${ROOT}/reports/agent_e2e_l3_20260601-130930.json`]);
  }

  // Slide 7 — code and hard parts
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "代码难点", "难点是让计划、状态与结果保持一致", 7);
    addText(slide, "工具白名单：模型没有执行权限", { left: 72, top: 158, width: 530, height: 34 }, { fontSize: 22, bold: true, color: C.primary });
    addShape(slide, "roundRect", { left: 72, top: 206, width: 536, height: 246 }, C.primaryDark, C.primaryDark, 1);
    addText(slide, "def parse_plan_steps(raw, allowed_tools):\n    steps = raw.get(\"steps\")\n    allowed = set(allowed_tools)\n\n    for step in steps:\n        tool = step.get(\"tool\")\n        if tool not in allowed:\n            raise ValueError(\n                f\"tool not allowed: {tool}\"\n            )", { left: 94, top: 226, width: 492, height: 204 }, {
      fontSize: 19, color: C.white, typeface: MONO, lineSpacing: 1.04,
    });
    addShape(slide, "roundRect", { left: 72, top: 478, width: 536, height: 150 }, C.light, C.line, 1);
    addBulletList(slide, [
      "ToolExecutor 再做 risk / schema / timeout / retry",
      "R0/R1/R2 已有确定性摘要时，禁止 LLM 重写数字",
      "Preview 缓存 Plan，Run 复用同一任务上下文",
    ], { left: 90, top: 494, width: 500, height: 118 }, { fontSize: 18, spaceAfter: 9 });

    const challenges = [
      ["01", "协作边界", "两层架构 + AgentTask / AgentResult\n依赖写在 Supervisor，不做自由群聊", C.primary],
      ["02", "工具安全", "allowed_tools + ToolSpec + Policy Gate\n模型决策与制造计算隔离", C.secondary],
      ["03", "上下文一致", "context_hash + Plan 缓存 + pending route\nMemory 不保存第二份业务事实", C.accent],
    ];
    challenges.forEach((ch, i) => {
      const y = 174 + i * 154;
      addShape(slide, "roundRect", { left: 662, top: y, width: 546, height: 132 }, C.white, ch[3], 1);
      addTag(slide, ch[0], { left: 682, top: y + 18, width: 52, height: 34 }, ch[3] === C.primary ? C.primaryPale : (ch[3] === C.secondary ? C.secondaryPale : C.accentPale), ch[3]);
      addText(slide, ch[1], { left: 752, top: y + 14, width: 184, height: 40 }, { fontSize: 24, bold: true, color: ch[3], valign: "middle" });
      addText(slide, ch[2], { left: 684, top: y + 62, width: 500, height: 52 }, { fontSize: 18, color: C.text, valign: "middle" });
    });
    addText(slide, "LLM 理解与决策｜Harness 约束与追踪｜Tool 确定性执行", { left: 662, top: 632, width: 546, height: 30 }, {
      fontSize: 16, bold: true, color: C.primaryDark, align: "center", valign: "middle",
    });
    addFooter(slide, "主讲结束 · 后续为 Backup");
    addNotes(slide,
      "最难的不是创建多个 Agent 类，而是控制协作边界。第一，用两层架构和统一协议避免自由群聊。第二，模型生成的 Tool 必须通过 allowed_tools，ToolExecutor 再做风险和 Schema 校验，关键数字不让 LLM 二次改写。第三，Preview、Run 和多轮续聊通过 context_hash、Plan 缓存和 pending route 使用同一任务状态。",
      [`${ROOT}/src/metaforge/planning_collab/supervisor.py`, `${ROOT}/src/metaforge/orchestrator/llm/parsers.py`, `${ROOT}/src/metaforge/harness/tool_executor.py`, `${ROOT}/src/metaforge/agents/base.py`, `${ROOT}/src/metaforge/harness/context.py`, `${ROOT}/src/metaforge/orchestrator/preview.py`, `${ROOT}/src/metaforge/memory/pending.py`]);
  }

  // Slide 8 — backup agent roles
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "角色分工", "六个业务 Agent 各自拥有独立责任边界", 8, true);
    const values = [
      ["Agent", "主要职责", "核心 Tool / 模块", "关键产物"],
      ["Scheduling", "正常排程与策略求解", "planning_collab / solver", "package"],
      ["Events", "故障、插单、改交期", "events.* / delivery.*", "impact_report"],
      ["Kitting", "BOM 齐套与缺料", "material.* / kitting.*", "kitting_report"],
      ["Commitment", "交期风险与客户说明", "delivery.*", "delivery_assessment"],
      ["What-if", "多策略与异常假设对比", "compare.variants", "what_if"],
      ["Plans", "计划库 CRUD 与绑定", "data.*", "active_plan"],
    ];
    const table = slide.tables.add({ rows: values.length, columns: 4, left: 72, top: 168, width: 1136, height: 388, values, columnWidths: [180, 300, 330, 326] });
    styleTable(table, values.length, 4, { fontSize: 17, headerFontSize: 18 });
    addShape(slide, "roundRect", { left: 72, top: 584, width: 1136, height: 66 }, C.primaryPale, C.primary, 1);
    addText(slide, "排程域内协作：Order 分析订单风险 · Constraint 生成硬/软约束 · Resource 分析瓶颈与负载", { left: 96, top: 596, width: 1088, height: 42 }, {
      fontSize: 20, bold: true, color: C.primaryDark, align: "center", valign: "middle",
    });
    addFooter(slide, "Backup · Agent Roles");
    addNotes(slide, "备用页，用于面试官追问六个 Agent 的具体分工。强调外层六岗与排程域内三个分析 Agent 是两层关系。", [`${ROOT}/src/metaforge/agents/registry_meta.py`, `${ROOT}/src/metaforge/planning_collab/agents`]);
  }

  // Slide 9 — backup capability catalog
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "能力接入", "Tool、策略、求解器与事件统一注册", 9, true);
    addStat(slide, "30 → 34", "业务 Tool\n项目阶段 → 当前", { left: 72, top: 174, width: 330, height: 132 }, C.primary, C.primaryPale);
    addStat(slide, "6 × 14", "策略模板 × 求解器", { left: 475, top: 174, width: 330, height: 132 }, C.secondary, C.secondaryPale);
    addStat(slide, "8 类", "动态异常事件", { left: 878, top: 174, width: 330, height: 132 }, C.accent, C.accentPale);
    addShape(slide, "roundRect", { left: 72, top: 338, width: 330, height: 288 }, C.white, C.line, 1);
    addText(slide, "Tool 域", { left: 96, top: 354, width: 282, height: 34 }, { fontSize: 22, bold: true, color: C.primary, align: "center" });
    addBulletList(slide, ["排程 4", "计划与落库 10", "异常与执行态 6", "交期 4", "物料齐套 4", "对比 1 · Memory 1", "后续 planning.* 4"], { left: 106, top: 402, width: 262, height: 204 }, { fontSize: 19, spaceAfter: 7 });
    addShape(slide, "roundRect", { left: 475, top: 338, width: 330, height: 288 }, C.white, C.line, 1);
    addText(slide, "Solver 家族", { left: 499, top: 354, width: 282, height: 34 }, { fontSize: 22, bold: true, color: C.secondary, align: "center" });
    addBulletList(slide, ["规则启发式 5", "SPT · LPT · MWKR · MOPNR · EDD", "元启发式 4", "TS · GA · SA · ACO", "RL / 实验型 5", "Q · DQN×2 · Neuroevo · PPO"], { left: 509, top: 402, width: 262, height: 204 }, { fontSize: 18, spaceAfter: 7 });
    addShape(slide, "roundRect", { left: 878, top: 338, width: 330, height: 288 }, C.white, C.line, 1);
    addText(slide, "Event 类型", { left: 902, top: 354, width: 282, height: 34 }, { fontSize: 22, bold: true, color: C.accent, align: "center" });
    addBulletList(slide, ["insert_order", "machine_breakdown", "due_date_change", "planned_downtime", "material_delay", "priority_change", "order_cancel · quantity_change"], { left: 912, top: 402, width: 262, height: 204 }, { fontSize: 17, spaceAfter: 7 });
    addFooter(slide, "Backup · Capability Catalog");
    addNotes(slide, "备用页，用于解释 30/34 Tool、6 种策略、14 个求解器与 8 类事件的具体构成。项目交付阶段口径为 30，当前新增 4 个 planning Tool。", [`${ROOT}/src/metaforge/tools`, `${ROOT}/src/metaforge/agent/scheduling_agent.py`, `${ROOT}/src/metaforge/utils/solver_registry.py`, `${ROOT}/src/metaforge/tools/events/list_event_types.py`]);
  }

  // Slide 10 — backup reliability matrix
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "稳定设计", "失败处理分布在四层", 10, true);
    const values = [
      ["层级", "主要风险", "处理机制"],
      ["Router", "GLM 误路由", "规则 Guard / session_continue"],
      ["Plan", "非法 Tool / 输出错误", "allowed_tools / rule_fallback"],
      ["Tool", "参数、权限、超时", "Schema / allow-ask-deny / retry"],
      ["Agent", "缺参数或低置信度", "clarify / need_input / human"],
      ["Solver", "主求解器失败", "fallback_solver"],
      ["Persist", "未经确认写库", "预览 + 15 min confirm_token"],
    ];
    const table = slide.tables.add({ rows: values.length, columns: 3, left: 72, top: 174, width: 1136, height: 390, values, columnWidths: [180, 390, 566] });
    styleTable(table, values.length, 3, { fontSize: 18, headerFontSize: 19 });
    addShape(slide, "roundRect", { left: 72, top: 592, width: 1136, height: 58 }, C.secondaryPale, C.secondary, 1);
    addText(slide, "边界说明：ToolExecutor 提供通用 timeout/retry；当前并非所有业务 Tool 都显式配置 retry_policy。", { left: 96, top: 602, width: 1088, height: 38 }, {
      fontSize: 18, bold: true, color: C.secondary, align: "center", valign: "middle",
    });
    addFooter(slide, "Backup · Reliability");
    addNotes(slide, "备用页，用于回答稳定性设计。注意平台能力和业务配置的区别：ToolExecutor 支持 timeout/retry，但不是所有 Tool 都配置自动重试。", [`${ROOT}/src/metaforge/harness/tool_executor.py`, `${ROOT}/src/metaforge/orchestrator/router.py`, `${ROOT}/src/metaforge/services/persist_store.py`, `${ROOT}/src/metaforge/strategy/solver_policy.py`]);
  }

  // Slide 11 — backup evaluation wording
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.white;
    addHeader(slide, "评测口径", "把理解、执行与环境问题分层看", 11, true);
    const values = [
      ["数据集", "通过", "失败", "跳过", "有效率"],
      ["L2 Preview · 65 条", "55", "8", "2", "87.3% · 55/63"],
      ["L3 核心冒烟 · 19 条", "14", "2", "3", "87.5% · 14/16"],
      ["L3 全量首轮 · 65 条", "32", "19", "14", "62.7% · 32/51"],
    ];
    const table = slide.tables.add({ rows: values.length, columns: 5, left: 72, top: 180, width: 1136, height: 220, values, columnWidths: [390, 150, 150, 150, 296] });
    styleTable(table, values.length, 5, { fontSize: 19, headerFontSize: 19 });
    addText(slide, "推荐表述", { left: 72, top: 436, width: 190, height: 32 }, { fontSize: 22, bold: true, color: C.accent });
    addShape(slide, "roundRect", { left: 72, top: 478, width: 1136, height: 114 }, C.accentPale, C.accent, 1);
    addText(slide, "建立 65 条标准业务需求的 L2/L3 分层评测；L2 Preview 有效率 87.3%，\nL3 核心冒烟 87.5%，异常重排 Agent 14 条端到端用例全部通过。", { left: 104, top: 498, width: 1072, height: 76 }, {
      fontSize: 24, bold: true, color: C.accent, align: "center", valign: "middle", lineSpacing: 1.08,
    });
    addText(slide, "不把 Preview、全量 Exec、跳过用例和“Tool 100%”混成同一口径。", { left: 72, top: 614, width: 1136, height: 34 }, {
      fontSize: 17, color: C.danger, align: "center", valign: "middle",
    });
    addFooter(slide, "Backup · Evaluation");
    addNotes(slide, "备用页，用于解释评测数字和失败归因。L2 的 87.3% 是 55/63；L3 核心 87.5% 是 14/16；全量首轮 32/51，需要如实说明。", [`${ROOT}/reports/agent_e2e_l2_20260601-114642.json`, `${ROOT}/reports/agent_e2e_l3_20260601-125055.json`, `${ROOT}/reports/agent_e2e_l3_20260601-130930.json`, `${ROOT}/docs/agent-effectiveness-evaluation.md`]);
  }

  // Export all previews and artifacts.
  for (const [index, slide] of presentation.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    const png = await presentation.export({ slide, format: "png", scale: 1.4 });
    await fs.writeFile(`${TMP}/${stem}.png`, new Uint8Array(await png.arrayBuffer()));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(`${TMP}/${stem}.layout.json`, await layout.text());
  }
  const montage = await presentation.export({ format: "webp", montage: true, scale: 1 });
  await fs.writeFile(`${TMP}/montage.webp`, new Uint8Array(await montage.arrayBuffer()));
  const inspect = await presentation.inspect({ kind: "slide,textbox,shape,table,notes", maxChars: 40000 });
  await fs.writeFile(`${TMP}/inspect.ndjson`, inspect.ndjson);
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(FINAL);
  console.log(JSON.stringify({ final: FINAL, slides: presentation.slides.items.length, montage: `${TMP}/montage.webp` }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
