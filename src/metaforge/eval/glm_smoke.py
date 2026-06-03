"""GLM 联调冒烟：scheduling / events 典型话术 → 路由 + Plan + trace。

用法:
  python -m metaforge.eval.glm_smoke
  python -m metaforge.eval.glm_smoke --exec
  python -m metaforge.eval.glm_smoke --json reports/glm_smoke.json

环境:
  ZHIPU_API_KEY  必填（真实 GLM 调用）
  LLM_ENABLED=1  LLM_ROUTER=glm（脚本会自动设置）
  可选 LLM_REACT_ENABLED=1 / LLM_REFLECT_ENABLED=1（--react / --reflect）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# 与 benchmark 一致的最小工单，供 --exec 排程/重排
DEFAULT_JOBS: List[Dict[str, Any]] = [
    {
        "name": "工单A",
        "priority": 10,
        "due_date": 20.0,
        "tasks": [
            {"name": "Op-1", "machine_id": 0, "duration": 3},
            {"name": "Op-2", "machine_id": 1, "duration": 2},
        ],
    },
    {
        "name": "订单106",
        "priority": 15,
        "due_date": 18.0,
        "tasks": [{"name": "Op-1", "machine_id": 0, "duration": 4}],
    },
    {
        "name": "工单B",
        "priority": 20,
        "due_date": 25.0,
        "tasks": [{"name": "Op-1", "machine_id": 1, "duration": 3}],
    },
]


@dataclass
class SmokeCase:
    id: str
    message: str
    domain: str
    expect_agent: Optional[str] = None
    intent: Optional[str] = None
    note: str = ""


@dataclass
class SmokeResult:
    case_id: str
    message: str
    domain: str
    ok: bool
    agent_id: str = ""
    router: str = ""
    router_intent: str = ""
    plan_planner: str = ""
    tools: List[str] = field(default_factory=list)
    parse_planner: str = ""
    status: str = "preview"
    summary_zh: str = ""
    route_lines: List[str] = field(default_factory=list)
    plan_lines: List[str] = field(default_factory=list)
    error: str = ""
    elapsed_ms: float = 0.0
    expect_agent: Optional[str] = None
    note: str = ""


SMOKE_CASES: List[SmokeCase] = [
    # --- scheduling ---
    SmokeCase("sch_tabu_delivery", "用禁忌搜索，交付优先排程", "scheduling", "scheduling", note="算法+策略"),
    SmokeCase("sch_compare_ga_sa", "对比一下遗传算法和模拟退火", "scheduling", "scheduling", note="多算法对比"),
    SmokeCase("sch_benchmark", "跑一下 ft06 算例，吞吐优先", "scheduling", "scheduling", note="标准算例"),
    SmokeCase("sch_fast", "快速先出个结果", "scheduling", "scheduling", note="快速模式"),
    SmokeCase("sch_vague", "帮我排一下", "scheduling", "scheduling", note="模糊意图，可能澄清"),
    SmokeCase("sch_full_compare", "按交期优先，全量对比所有算法", "scheduling", "scheduling", note="目标驱动全量对比"),
    SmokeCase("sch_no_material", "用 SPT 排程，不考虑物料", "scheduling", "scheduling", note="关闭物料"),
    SmokeCase("sch_explicit", "排程", "scheduling", "scheduling", intent="schedule", note="显式 intent"),
    # --- events ---
    SmokeCase("evt_breakdown", "3号机坏了4小时", "events", "events", note="设备故障"),
    SmokeCase("evt_insert", "紧急插单", "events", "events", note="插单"),
    SmokeCase("evt_due_date", "订单106交期改为20", "events", "events", note="改交期"),
    SmokeCase("evt_downtime", "1号机停机大修8小时", "events", "events", note="计划停机"),
    SmokeCase("evt_priority", "工单A加急", "events", "events", note="优先级"),
    SmokeCase("evt_catalog", "支持哪些异常", "events", "events", note="事件类型列表"),
    SmokeCase("evt_material_delay", "物料延迟24小时", "events", "events", note="到料延迟"),
    SmokeCase("evt_cancel", "撤单工单B", "events", "events", note="撤单"),
    # --- 路由干扰项 ---
    SmokeCase("route_plans", "新建计划试产01", "plans", "plans", note="应进 plans 而非 scheduling"),
    # --- kitting / commitment / whatif ---
    SmokeCase("kit_check", "检查一下齐套能否开工", "kitting", "kitting", note="齐套检查"),
    SmokeCase("cmt_risk", "交期能不能满足客户", "commitment", "commitment", note="交期承诺问询"),
    SmokeCase("wif_strategies", "对比一下交付优先和吞吐优先两种策略", "whatif", "whatif", note="策略方案对比"),
    # --- scheduling 落库（原 pipeline）---
    SmokeCase(
        "sched_persist",
        "把这个计划排程并保存落库",
        "scheduling",
        "scheduling",
        note="排程+提议落库",
    ),
]


def _trace_block(preview: Dict[str, Any], phase: str) -> Dict[str, Any]:
    for block in preview.get("trace") or []:
        if block.get("phase") == phase:
            return block
    return {}


def _tools_from_preview(preview: Dict[str, Any]) -> List[str]:
    plan = _trace_block(preview, "plan")
    return [str(s.get("tool")) for s in plan.get("steps") or [] if s.get("tool")]


def _parse_planner_from_preview(preview: Dict[str, Any]) -> str:
    parse = _trace_block(preview, "parse")
    lines = parse.get("lines") or []
    for line in lines:
        if "planner" in str(line).lower() or "GLM" in str(line) or "规则" in str(line):
            return str(line)[:120]
    return ""


def _apply_llm_env(*, react: bool, reflect: bool) -> None:
    os.environ["LLM_ENABLED"] = "1"
    os.environ["LLM_ROUTER"] = "glm"
    os.environ.setdefault("LLM_FALLBACK", "rule")
    os.environ.setdefault("LLM_PLAN_ENABLED", "1")
    os.environ.setdefault(
        "LLM_PLAN_AGENTS", "scheduling,events,kitting,commitment,whatif"
    )
    if react:
        os.environ["LLM_REACT_ENABLED"] = "1"
        os.environ.setdefault("LLM_REACT_AGENTS", "scheduling,events")
    else:
        os.environ["LLM_REACT_ENABLED"] = "0"
    if reflect:
        os.environ["LLM_REFLECT_ENABLED"] = "1"
    else:
        os.environ["LLM_REFLECT_ENABLED"] = "0"


def _check_api_key() -> Optional[str]:
    key = (os.getenv("ZHIPU_API_KEY") or "").strip()
    if not key:
        return "未设置 ZHIPU_API_KEY，无法调用 GLM。请在 .env 中配置后重试。"
    return None


def run_preview_case(case: SmokeCase) -> SmokeResult:
    from metaforge.orchestrator.preview import build_orchestrator_preview

    t0 = time.perf_counter()
    err = ""
    preview: Dict[str, Any] = {}
    try:
        preview = build_orchestrator_preview(
            case.message,
            case.intent,
            context={"custom_data": DEFAULT_JOBS},
        )
    except Exception as e:
        err = str(e)[:400]

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    route = preview.get("route") or {}
    agent_id = preview.get("agent_id") or route.get("agent_id") or ""
    route_blk = _trace_block(preview, "route")
    plan_blk = _trace_block(preview, "plan")
    tools = _tools_from_preview(preview)
    ok = not err and (case.expect_agent is None or agent_id == case.expect_agent)

    return SmokeResult(
        case_id=case.id,
        message=case.message,
        domain=case.domain,
        ok=ok,
        agent_id=agent_id,
        router=str(route.get("router") or preview.get("router_planner") or ""),
        router_intent=str(route.get("intent") or preview.get("router_intent") or ""),
        plan_planner=str(preview.get("plan_planner") or plan_blk.get("planner") or ""),
        tools=tools,
        parse_planner=_parse_planner_from_preview(preview),
        status="preview",
        route_lines=list(route_blk.get("lines") or [])[:8],
        plan_lines=list(plan_blk.get("lines") or [])[:8],
        error=err,
        elapsed_ms=elapsed,
        expect_agent=case.expect_agent,
        note=case.note,
    )


def run_exec_case(case: SmokeCase) -> SmokeResult:
    from metaforge.agents.base import AgentRequest
    from metaforge.orchestrator.router import get_agent, resolve_agent_route

    t0 = time.perf_counter()
    err = ""
    agent_id = ""
    plan_planner = ""
    tools: List[str] = []
    summary = ""
    status = "failed"
    route: Dict[str, Any] = {}

    try:
        route = resolve_agent_route(case.message, case.intent)
        agent_id = route.get("agent_id") or ""
        agent = get_agent(agent_id)
        areq = AgentRequest(
            message=case.message,
            params={"use_llm": True},
            context={
                "custom_data": DEFAULT_JOBS,
                "session_id": f"glm_smoke_{case.id}",
            },
        )
        resp = agent.run(areq)
        status = resp.status
        summary = resp.summary_zh or ""
        plan_planner = resp.plan_planner or getattr(agent, "_plan_planner", "")
        tools = [str(p.get("tool")) for p in resp.plan or [] if p.get("tool")]
    except Exception as e:
        err = str(e)[:400]

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    ok = (
        not err
        and status in ("success", "need_input", "pending_clarification", "pending_confirm")
        and (case.expect_agent is None or agent_id == case.expect_agent)
    )

    return SmokeResult(
        case_id=case.id,
        message=case.message,
        domain=case.domain,
        ok=ok,
        agent_id=agent_id,
        router=str(route.get("router") or ""),
        router_intent=str(route.get("intent") or ""),
        plan_planner=plan_planner,
        tools=tools,
        status=status,
        summary_zh=summary[:200],
        error=err,
        elapsed_ms=elapsed,
        expect_agent=case.expect_agent,
        note=case.note,
    )


def run_smoke(
    *,
    domain: str = "all",
    exec_mode: bool = False,
    react: bool = False,
    reflect: bool = False,
    limit: Optional[int] = None,
    verbose: bool = True,
) -> List[SmokeResult]:
    from metaforge.tools.load_all import load_all_tools

    load_all_tools()
    _apply_llm_env(react=react, reflect=reflect)

    cases = SMOKE_CASES
    if domain != "all":
        cases = [c for c in cases if c.domain == domain]
    if limit is not None and limit > 0:
        cases = cases[:limit]

    runner = run_exec_case if exec_mode else run_preview_case
    results: List[SmokeResult] = []
    for i, case in enumerate(cases, 1):
        if verbose:
            print(f"[{i}/{len(cases)}] {case.id}: {case.message[:40]}…", flush=True)
        results.append(runner(case))
        if verbose:
            r = results[-1]
            mark = "OK" if r.ok else "FAIL"
            print(
                f"    -> {mark} agent={r.agent_id} router={r.router} "
                f"plan={r.plan_planner} tools={len(r.tools)} {r.elapsed_ms:.0f}ms",
                flush=True,
            )
    return results


def format_report(results: List[SmokeResult], *, exec_mode: bool) -> str:
    mode = "端到端执行" if exec_mode else "Preview（路由+Plan+解析）"
    passed = sum(1 for r in results if r.ok)
    failed = sum(1 for r in results if not r.ok)
    lines = [
        "=== MetaForge GLM 联调冒烟 ===",
        f"模式: {mode}",
        f"时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"模型: {os.getenv('ZHIPU_MODEL', 'glm-4.5-air')}",
        f"ReAct: {os.getenv('LLM_REACT_ENABLED', '0')}  Reflect: {os.getenv('LLM_REFLECT_ENABLED', '0')}",
        f"通过: {passed}/{len(results)}  失败: {failed}",
        "",
    ]

    for domain in (
        "scheduling",
        "events",
        "plans",
        "kitting",
        "commitment",
        "whatif",
    ):
        subset = [r for r in results if r.domain == domain]
        if not subset:
            continue
        lines.append(f"## {domain} ({len(subset)} 条)")
        lines.append(
            "| id | 话术 | agent | router | plan_planner | tools | ms | ok |"
        )
        lines.append("|----|------|-------|--------|--------------|-------|----|----|")
        for r in subset:
            tools = " → ".join(r.tools[:4]) if r.tools else "—"
            if len(r.tools) > 4:
                tools += "…"
            msg = r.message[:20] + ("…" if len(r.message) > 20 else "")
            ok_mark = "OK" if r.ok else "FAIL"
            lines.append(
                f"| {r.case_id} | {msg} | {r.agent_id} | {r.router} | "
                f"{r.plan_planner} | {tools} | {r.elapsed_ms:.0f} | {ok_mark} |"
            )
        lines.append("")

    failures = [r for r in results if not r.ok]
    if failures:
        lines.append("## 失败详情")
        for r in failures:
            lines.append(f"### {r.case_id} — {r.message}")
            if r.expect_agent:
                lines.append(f"- 期望 agent: {r.expect_agent}，实际: {r.agent_id or '—'}")
            if r.error:
                lines.append(f"- error: {r.error}")
            if r.route_lines:
                lines.append("- route: " + " / ".join(r.route_lines[:3]))
            if r.note:
                lines.append(f"- note: {r.note}")
            lines.append("")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MetaForge GLM 联调冒烟")
    parser.add_argument(
        "--domain",
        choices=("all", "scheduling", "events", "plans"),
        default="all",
        help="只跑某一域用例",
    )
    parser.add_argument(
        "--exec",
        action="store_true",
        help="端到端执行 Agent（较慢，会调用求解器）",
    )
    parser.add_argument("--react", action="store_true", help="启用 LLM_REACT_ENABLED=1")
    parser.add_argument("--reflect", action="store_true", help="启用 LLM_REFLECT_ENABLED=1（需 --react）")
    parser.add_argument("--json", type=str, default="", help="另存 JSON 报告路径")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全部）")
    parser.add_argument("-q", "--quiet", action="store_true", help="不打印逐条进度")
    args = parser.parse_args(argv)

    key_err = _check_api_key()
    if key_err:
        print(key_err, file=sys.stderr)
        print("提示: 复制 .env.example 为 .env 并填入 ZHIPU_API_KEY", file=sys.stderr)
        return 2

    results = run_smoke(
        domain=args.domain,
        exec_mode=args.exec,
        react=args.react,
        reflect=args.reflect,
        limit=args.limit if args.limit > 0 else None,
        verbose=not args.quiet,
    )
    text = format_report(results, exec_mode=args.exec)
    print(text)

    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "exec_mode": args.exec,
            "react": args.react,
            "reflect": args.reflect,
            "results": [asdict(r) for r in results],
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 已写入: {out_path.resolve()}")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
