"""Agent 基准评测：意图路由、计划 Tool 链、可选端到端执行。

用法:
  python -m metaforge.eval.agent_benchmark
  pytest tests/test_agent_benchmark.py -v
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

_DEFAULT_YAML = (
    Path(__file__).resolve().parents[3] / "tests" / "data" / "agent_benchmark.yaml"
)


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    dimension: str
    message: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class BenchmarkReport:
    results: List[CaseResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed and not r.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed and not r.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)

    def rate(self, dimension: Optional[str] = None) -> float:
        items = [
            r
            for r in self.results
            if not r.skipped and (dimension is None or r.dimension == dimension)
        ]
        if not items:
            return 0.0
        return sum(1 for r in items if r.passed) / len(items)

    def by_dimension(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for r in self.results:
            bucket = out.setdefault(r.dimension, {"pass": 0, "fail": 0, "skip": 0})
            if r.skipped:
                bucket["skip"] += 1
            elif r.passed:
                bucket["pass"] += 1
            else:
                bucket["fail"] += 1
        return out

    def failures(self) -> List[CaseResult]:
        return [r for r in self.results if not r.passed and not r.skipped]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": {
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
                "by_dimension": self.by_dimension(),
            },
            "results": [
                {
                    "case_id": r.case_id,
                    "passed": r.passed,
                    "skipped": r.skipped,
                    "skip_reason": r.skip_reason,
                    "dimension": r.dimension,
                    "message": r.message,
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }


def load_benchmark_cases(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = path or _DEFAULT_YAML
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return list(data.get("cases") or [])


def _should_skip_case(case: Dict[str, Any]) -> Optional[str]:
    mode = (case.get("router_mode") or "rule").strip().lower()
    if mode == "llm" and os.getenv("RUN_LLM_BENCHMARK", "").strip() not in ("1", "true", "yes"):
        return "RUN_LLM_BENCHMARK 未开启（GLM 路由用例）"
    tier = (case.get("tier") or "preview").strip().lower()
    if tier == "run" and os.getenv("RUN_AGENT_BENCHMARK_EXEC", "").strip() not in (
        "1",
        "true",
        "yes",
    ):
        return "RUN_AGENT_BENCHMARK_EXEC 未开启（端到端执行用例）"
    return None


def _plan_tools_from_preview(preview: Dict[str, Any]) -> List[str]:
    for block in preview.get("trace") or []:
        if block.get("phase") == "plan":
            return [str(s.get("tool")) for s in block.get("steps") or [] if s.get("tool")]
    return []


def _tools_match(actual: List[str], expect: List[str], *, exact: bool) -> bool:
    if exact:
        return actual == expect
    return all(t in actual for t in expect)


def eval_route_case(case: Dict[str, Any]) -> CaseResult:
    from metaforge.orchestrator.router import resolve_agent_route

    cid = case["id"]
    message = case.get("message") or ""
    intent = case.get("intent")
    mode = (case.get("router_mode") or "rule").strip().lower()

    prev_llm = os.environ.get("LLM_ENABLED")
    prev_router = os.environ.get("LLM_ROUTER")
    try:
        if mode == "rule":
            os.environ["LLM_ENABLED"] = "0"
            os.environ["LLM_ROUTER"] = "rule"
        elif mode == "llm":
            os.environ["LLM_ENABLED"] = "1"
            os.environ["LLM_ROUTER"] = "glm"
            if not os.getenv("ZHIPU_API_KEY"):
                return CaseResult(
                    cid,
                    False,
                    "route",
                    "缺少 ZHIPU_API_KEY",
                    skipped=True,
                    skip_reason="未配置 API Key",
                )
        route = resolve_agent_route(message, intent)
    finally:
        if prev_llm is None:
            os.environ.pop("LLM_ENABLED", None)
        else:
            os.environ["LLM_ENABLED"] = prev_llm
        if prev_router is None:
            os.environ.pop("LLM_ROUTER", None)
        else:
            os.environ["LLM_ROUTER"] = prev_router

    expect_agent = case.get("expect_agent")
    expect_intent = case.get("expect_intent")
    ok = route.get("agent_id") == expect_agent
    if expect_intent is not None:
        ok = ok and route.get("intent") == expect_intent

    return CaseResult(
        cid,
        ok,
        "route",
        "" if ok else f"期望 agent={expect_agent} intent={expect_intent}",
        detail={
            "actual_agent": route.get("agent_id"),
            "actual_intent": route.get("intent"),
            "router": route.get("router"),
            "message": message,
        },
    )


def eval_plan_case(case: Dict[str, Any]) -> CaseResult:
    from metaforge.orchestrator.preview import build_orchestrator_preview

    cid = case["id"]
    os.environ["LLM_ENABLED"] = "0"
    preview = build_orchestrator_preview(
        case.get("message") or "",
        case.get("intent"),
        params=dict(case.get("params") or {}),
    )
    actual_agent = preview.get("agent_id")
    tools = _plan_tools_from_preview(preview)
    expect_agent = case.get("expect_agent")
    expect_tools = list(case.get("expect_tools") or [])
    exact = bool(case.get("expect_tools_exact"))

    ok = actual_agent == expect_agent
    if expect_tools:
        ok = ok and _tools_match(tools, expect_tools, exact=exact)

    return CaseResult(
        cid,
        ok,
        "plan",
        "" if ok else "计划 Tool 链与期望不符",
        detail={
            "actual_agent": actual_agent,
            "actual_tools": tools,
            "expect_tools": expect_tools,
            "plan_planner": preview.get("plan_planner"),
        },
    )


def eval_run_case(
    case: Dict[str, Any],
    *,
    run_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    session_ids: Dict[str, str],
) -> CaseResult:
    cid = case["id"]
    body: Dict[str, Any] = {
        "message": case.get("message") or "",
        "intent": case.get("intent"),
        "params": dict(case.get("params") or {}),
        "context": dict(case.get("context") or {}),
    }
    dep = case.get("requires_session_from")
    if dep:
        sid = session_ids.get(dep)
        if not sid:
            return CaseResult(
                cid,
                False,
                "run",
                f"依赖会话 {dep} 不存在",
                detail={"depends_on": dep},
            )
        body["context"]["session_id"] = sid

    data = run_fn(body)
    expect_agent = case.get("expect_agent")
    expect_status = case.get("expect_status", "success")
    ok = data.get("agent_id") == expect_agent and data.get("status") == expect_status
    if data.get("session_id"):
        session_ids[cid] = str(data["session_id"])

    return CaseResult(
        cid,
        ok,
        "run",
        "" if ok else f"期望 status={expect_status} agent={expect_agent}",
        detail={
            "actual_status": data.get("status"),
            "actual_agent": data.get("agent_id"),
            "error": data.get("error"),
            "plan_steps": len(data.get("plan") or []),
            "failed_steps": [
                s for s in (data.get("plan") or []) if s.get("status") == "failed"
            ],
        },
    )


def run_benchmark(
    cases: Optional[List[Dict[str, Any]]] = None,
    *,
    run_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    min_jobs: Optional[List[Dict[str, Any]]] = None,
) -> BenchmarkReport:
    """运行全部用例并汇总报告。"""
    from metaforge.tools.load_all import load_all_tools

    load_all_tools()
    report = BenchmarkReport()
    session_ids: Dict[str, str] = {}

    if min_jobs is None:
        min_jobs = [
            {
                "name": "BM-工单",
                "priority": 10,
                "due_date": 12.0,
                "tasks": [
                    {"machine_id": 0, "duration": 2},
                    {"machine_id": 1, "duration": 2},
                ],
            }
        ]

    for case in cases or load_benchmark_cases():
        cid = case.get("id") or "?"
        skip = _should_skip_case(case)
        if skip:
            tier = (case.get("tier") or "preview").lower()
            if tier == "run":
                dim = "run"
            elif case.get("expect_tools"):
                dim = "plan"
            else:
                dim = "route"
            report.results.append(
                CaseResult(cid, True, dim, skipped=True, skip_reason=skip)
            )
            continue

        tier = (case.get("tier") or "preview").strip().lower()
        if tier == "run":
            if run_fn is None:
                report.results.append(
                    CaseResult(
                        cid,
                        False,
                        "run",
                        "未提供 run_fn",
                        skipped=True,
                        skip_reason="无 HTTP 客户端",
                    )
                )
                continue
            body_ctx = case.setdefault("context", {})
            if "custom_data" not in body_ctx and not case.get("requires_session_from"):
                body_ctx["custom_data"] = min_jobs
            report.results.append(eval_run_case(case, run_fn=run_fn, session_ids=session_ids))
            continue

        if case.get("expect_tools"):
            report.results.append(eval_plan_case(case))
        else:
            report.results.append(eval_route_case(case))

    return report


def format_report_text(report: BenchmarkReport) -> str:
    lines = [
        "=== MetaForge Agent Benchmark ===",
        f"通过: {report.passed}  失败: {report.failed}  跳过: {report.skipped}",
        "",
    ]
    for dim, label in [
        ("route", "意图路由"),
        ("plan", "计划 Tool 链"),
        ("run", "端到端执行"),
    ]:
        bucket = report.by_dimension().get(dim)
        if not bucket:
            continue
        total = bucket["pass"] + bucket["fail"]
        rate = (bucket["pass"] / total * 100) if total else 0.0
        lines.append(f"[{label}] 通过率 {rate:.0f}% ({bucket['pass']}/{total})，跳过 {bucket['skip']}")

    fails = report.failures()
    if fails:
        lines.append("\n--- 失败明细 ---")
        for r in fails:
            lines.append(f"  ✗ {r.case_id} ({r.dimension}): {r.message}")
            for k, v in (r.detail or {}).items():
                lines.append(f"      {k}: {v}")
    return "\n".join(lines)


def main() -> None:
    report = run_benchmark()
    print(format_report_text(report))
    out = os.getenv("AGENT_BENCHMARK_JSON")
    if out:
        Path(out).write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON 已写入 {out}")


if __name__ == "__main__":
    main()
