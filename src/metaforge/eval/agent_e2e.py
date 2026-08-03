"""Agent GLM 联调 + 端到端执行评测。

用法:
  RUN_GLM_PREVIEW=1 python -m metaforge.eval.agent_e2e --tier preview
  RUN_GLM_EXEC=1 python -m metaforge.eval.agent_e2e --tier exec
  python -m metaforge.eval.agent_e2e --tier preview --tags scheduling --limit 3
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

import yaml

_DATA_ROOT = Path(__file__).resolve().parents[3] / "tests" / "data" / "agent_e2e"
_L2_YAML = _DATA_ROOT / "l2_preview.yaml"
_L3_YAML = _DATA_ROOT / "l3_exec.yaml"
_FIXTURES = _DATA_ROOT / "fixtures"


@dataclass
class E2eCaseResult:
    case_id: str
    ok: bool
    tier: str
    message: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    skip_reason: str = ""
    elapsed_ms: float = 0.0
    tags: List[str] = field(default_factory=list)


@dataclass
class E2eReport:
    tier: str
    results: List[E2eCaseResult] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok and not r.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok and not r.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)

    def failures(self) -> List[E2eCaseResult]:
        return [r for r in self.results if not r.ok and not r.skipped]

    def rate(self) -> float:
        active = [r for r in self.results if not r.skipped]
        if not active:
            return 0.0
        return sum(1 for r in active if r.ok) / len(active)

    def by_tag(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for r in self.results:
            for tag in r.tags or ["untagged"]:
                bucket = out.setdefault(tag, {"pass": 0, "fail": 0, "skip": 0})
                if r.skipped:
                    bucket["skip"] += 1
                elif r.ok:
                    bucket["pass"] += 1
                else:
                    bucket["fail"] += 1
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meta": self.meta,
            "summary": {
                "tier": self.tier,
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
                "rate": round(self.rate(), 4),
                "by_tag": self.by_tag(),
            },
            "results": [asdict(r) for r in self.results],
        }


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def _check_api_key() -> Optional[str]:
    if not (os.getenv("ZHIPU_API_KEY") or "").strip():
        return "未设置 ZHIPU_API_KEY"
    return None


def _apply_llm_env(*, react: bool = False, reflect: bool = False) -> None:
    os.environ["LLM_ENABLED"] = "1"
    os.environ["LLM_ROUTER"] = "glm"
    os.environ.setdefault("LLM_FALLBACK", "rule")
    os.environ.setdefault("LLM_PLAN_ENABLED", "1")
    os.environ.setdefault(
        "LLM_PLAN_AGENTS", "scheduling,kitting,commitment,whatif"
    )
    os.environ["LLM_REACT_ENABLED"] = "1" if react else "0"
    os.environ["LLM_REFLECT_ENABLED"] = "1" if (react and reflect) else "0"


def load_cases(
    tier: str,
    *,
    path: Optional[Path] = None,
    tags: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if path is None:
        path = _L2_YAML if tier == "preview" else _L3_YAML
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cases = list(data.get("cases") or [])
    if tags:
        tag_set = {t.strip() for t in tags if t.strip()}
        cases = [c for c in cases if tag_set.intersection(set(c.get("tags") or []))]
    if limit is not None and limit > 0:
        cases = cases[:limit]
    return cases


def load_fixture(name: str) -> Any:
    p = _FIXTURES / f"{name}.json"
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _allowed_tools_for(agent_id: str) -> List[str]:
    from metaforge.agents.registry_meta import AGENT_REGISTRY

    for entry in AGENT_REGISTRY:
        if entry.get("id") == agent_id:
            return list(entry.get("allowed_tools") or [])
    return []


def _e2e_run_all_cases() -> bool:
    """L3 全量跑时默认包含 slow / mongo（可用 AGENT_E2E_LITE=1 恢复跳过）。"""
    if _env_truthy("AGENT_E2E_LITE"):
        return False
    return _env_truthy("RUN_GLM_EXEC") or _env_truthy("AGENT_E2E_FULL")


def _should_skip_case(case: Dict[str, Any], *, tier: str) -> Optional[str]:
    run_all = _e2e_run_all_cases()
    skip_unless = case.get("skip_unless")
    if skip_unless and not _env_truthy(str(skip_unless)):
        if not (run_all and str(skip_unless) == "AGENT_E2E_MONGO"):
            return f"{skip_unless} 未开启"

    if "slow" in (case.get("tags") or []) and not _env_truthy("AGENT_E2E_SLOW"):
        if not run_all:
            return "AGENT_E2E_SLOW 未开启（慢用例）"

    if tier == "preview" and not _env_truthy("RUN_GLM_PREVIEW"):
        return "RUN_GLM_PREVIEW 未开启"

    if tier == "exec" and not _env_truthy("RUN_GLM_EXEC"):
        return "RUN_GLM_EXEC 未开启"

    if _check_api_key():
        return "未配置 ZHIPU_API_KEY"

    return None


def _e2e_default_extras(*, with_materials: bool = False) -> Dict[str, Any]:
    """E2E 注入内存物料/资源，避免长序列 TestClient 后 Motor 事件循环失效。"""
    from copy import deepcopy

    from metaforge.services.materials_inventory import DEFAULT_MATERIALS
    from metaforge.services.resource_config import default_resource_config

    extras: Dict[str, Any] = {"resource_config": default_resource_config()}
    if with_materials:
        catalog = deepcopy(DEFAULT_MATERIALS)
        extras["material_catalog"] = catalog
        extras["inventory"] = {m["id"]: float(m.get("current_stock", 0)) for m in catalog}
        extras["material_names"] = {m["id"]: m.get("name", m["id"]) for m in catalog}
    return extras


_E2E_PLAN_IDS: Dict[str, str] = {}


def _warm_e2e_app() -> None:
    """拉起 FastAPI lifespan（内存 plan_store），并写入种子计划。"""
    os.environ.setdefault("AGENT_E2E", "1")
    from fastapi.testclient import TestClient

    with TestClient(_load_fastapi_app()):
        pass
    _ensure_e2e_plan_store_seeded()


def _ensure_e2e_plan_store_seeded() -> Dict[str, str]:
    global _E2E_PLAN_IDS
    if _E2E_PLAN_IDS:
        return _E2E_PLAN_IDS
    from metaforge.services import plan_store
    from metaforge.services.plan_store_memory import seed_default_e2e_plans

    if not plan_store.is_configured():
        return {}
    _E2E_PLAN_IDS = seed_default_e2e_plans(load_fixture("min_jobs"))
    return _E2E_PLAN_IDS


def _build_context(case: Dict[str, Any]) -> Dict[str, Any]:
    ctx = dict(case.get("context") or {})
    e2e_plan_name = ctx.pop("e2e_plan_name", None)
    fixture_name = ctx.pop("fixture", None)
    if fixture_name:
        fixture = load_fixture(str(fixture_name))
        if isinstance(fixture, list):
            ctx.setdefault("custom_data", fixture)
        elif isinstance(fixture, dict):
            if "custom_data" in fixture:
                ctx.setdefault("custom_data", fixture["custom_data"])
            if "baseline_gantt" in fixture:
                ctx.setdefault("extras", {})
                ctx["extras"]["baseline_gantt"] = fixture["baseline_gantt"]
            if "sim_time" in fixture:
                ctx.setdefault("extras", {})
                ctx["extras"]["sim_time"] = fixture["sim_time"]
    if case.get("tier") == "exec":
        mes = load_fixture("mes_baseline") if fixture_name == "mes_baseline" else None
        if mes and isinstance(mes, dict) and mes.get("baseline_gantt"):
            params = case.setdefault("params", {})
            envelope = params.get("event_envelope")
            if isinstance(envelope, dict):
                ro = envelope.setdefault("reschedule_options", {})
                ro.setdefault("baseline_gantt", mes["baseline_gantt"])
                ro.setdefault("baseline_solver", "spt")
                envelope.setdefault("base_jobs", mes.get("custom_data") or [])
    if case.get("tier") == "exec":
        tags = set(case.get("tags") or [])
        agent = case.get("expect_agent")
        need_materials = agent == "kitting" or "kitting" in tags
        defaults = _e2e_default_extras(with_materials=need_materials)
        ctx.setdefault("extras", {})
        for key, val in defaults.items():
            ctx["extras"].setdefault(key, val)
    if e2e_plan_name and case.get("tier") == "exec":
        plan_ids = _ensure_e2e_plan_store_seeded()
        pid = plan_ids.get(str(e2e_plan_name))
        if pid:
            ctx["plan_id"] = pid
    return ctx


def _trace_block(preview: Dict[str, Any], phase: str) -> Dict[str, Any]:
    for block in preview.get("trace") or []:
        if block.get("phase") == phase:
            return block
    return {}


def _tools_from_preview(preview: Dict[str, Any]) -> List[str]:
    plan = _trace_block(preview, "plan")
    return [str(s.get("tool")) for s in plan.get("steps") or [] if s.get("tool")]


def _tools_match(actual: List[str], expect: List[str], *, ordered: bool) -> bool:
    if ordered:
        return actual == expect
    return all(t in actual for t in expect)


def _tools_one_of(actual: List[str], groups: List[List[str]]) -> bool:
    return any(_tools_match(actual, group, ordered=False) for group in groups)


def _get_nested(data: Dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _validate_tools_whitelist(agent_id: str, tools: List[str]) -> Optional[str]:
    allowed = set(_allowed_tools_for(agent_id))
    if not allowed:
        return None
    bad = [t for t in tools if t not in allowed]
    if bad:
        return f"Tool 越白名单: {bad}"
    return None


def run_l2_case(case: Dict[str, Any]) -> E2eCaseResult:
    from metaforge.orchestrator.preview import build_orchestrator_preview

    cid = case["id"]
    t0 = time.perf_counter()
    err = ""
    preview: Dict[str, Any] = {}
    try:
        preview = build_orchestrator_preview(
            case.get("message") or "",
            case.get("intent"),
            context=_build_context(case),
            params=dict(case.get("params") or {}),
        )
    except Exception as exc:
        err = str(exc)[:400]

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    route = preview.get("route") or {}
    agent_id = preview.get("agent_id") or route.get("agent_id") or ""
    tools = _tools_from_preview(preview)
    plan_planner = preview.get("plan_planner") or _trace_block(preview, "plan").get("planner") or ""
    router = str(route.get("router") or preview.get("router_planner") or "")

    failures: List[str] = []
    if err:
        failures.append(err)

    expect_agent = case.get("expect_agent")
    if expect_agent and agent_id != expect_agent:
        failures.append(f"agent: 期望 {expect_agent}, 实际 {agent_id}")

    expect_intent = case.get("expect_intent")
    if expect_intent and route.get("intent") != expect_intent:
        failures.append(f"intent: 期望 {expect_intent}, 实际 {route.get('intent')}")

    expect_router = case.get("expect_router")
    if expect_router and router != expect_router:
        failures.append(f"router: 期望 {expect_router}, 实际 {router}")

    expect_tools = list(case.get("expect_tools") or [])
    if expect_tools and not _tools_match(tools, expect_tools, ordered=bool(case.get("expect_tools_ordered"))):
        failures.append(f"tools 缺少: 期望包含 {expect_tools}, 实际 {tools}")

    one_of = case.get("expect_tools_one_of") or []
    if one_of and not _tools_one_of(tools, one_of):
        failures.append(f"tools one_of 未命中: {one_of}, 实际 {tools}")

    expect_planner = case.get("expect_plan_planner")
    if expect_planner and expect_planner != "any" and plan_planner != expect_planner:
        failures.append(f"plan_planner: 期望 {expect_planner}, 实际 {plan_planner}")

    wl_err = _validate_tools_whitelist(agent_id, tools) if tools else None
    if wl_err:
        failures.append(wl_err)

    max_ms = float(case.get("max_ms") or 90000)
    if elapsed > max_ms:
        failures.append(f"超时: {elapsed}ms > {max_ms}ms")

    return E2eCaseResult(
        case_id=cid,
        ok=not failures,
        tier="preview",
        message="; ".join(failures),
        detail={
            "agent_id": agent_id,
            "router": router,
            "router_intent": route.get("intent"),
            "plan_planner": plan_planner,
            "tools": tools,
            "error": err,
        },
        elapsed_ms=elapsed,
        tags=list(case.get("tags") or []),
    )


def _check_artifacts(data: Dict[str, Any], case: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    artifacts = data.get("artifacts") or {}
    for key in case.get("expect_artifacts_keys") or []:
        if key not in artifacts:
            failures.append(f"artifacts 缺少键: {key}")
            continue
        val = artifacts[key]
        if key == "schedule_results" and isinstance(val, dict) and not val:
            failures.append("schedule_results 为空")
        if key == "impact_report" and isinstance(val, dict):
            if case.get("expect_impact_gantt") and not (
                val.get("r1_gantt") or val.get("r2_gantt") or val.get("scenarios")
            ):
                failures.append("impact_report 缺少甘特/场景")
        if key == "delivery_assessment" and val is None:
            failures.append("delivery_assessment 为空")

    for dotted in case.get("expect_artifact_paths") or []:
        if _get_nested(artifacts, dotted) is None:
            failures.append(f"artifacts 路径缺失: {dotted}")

    min_summary = case.get("expect_summary_min_len")
    if min_summary:
        summary = data.get("summary_zh") or ""
        if len(summary) < int(min_summary):
            failures.append(f"summary_zh 过短: {len(summary)}")
    return failures


def run_l3_case(
    case: Dict[str, Any],
    *,
    run_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    session_ids: Dict[str, str],
) -> E2eCaseResult:
    cid = case["id"]
    t0 = time.perf_counter()
    body: Dict[str, Any] = {
        "message": case.get("message") or "",
        "intent": case.get("intent"),
        "params": dict(case.get("params") or {}),
        "context": _build_context(case),
    }
    params = body["params"]
    if case.get("intent") and not (case.get("message") or "").strip():
        params.setdefault("_skip_vague_clarify", True)
    if not params.get("skip_parse"):
        params.setdefault("use_llm", True)
    dep = case.get("requires_session_from")
    if dep:
        sid = session_ids.get(dep)
        if not sid:
            return E2eCaseResult(
                case_id=cid,
                ok=False,
                tier="exec",
                message=f"依赖会话 {dep} 不存在",
                detail={"depends_on": dep},
                tags=list(case.get("tags") or []),
            )
        body["context"]["session_id"] = sid

    err = ""
    data: Dict[str, Any] = {}
    try:
        data = run_fn(body)
    except Exception as exc:
        err = str(exc)[:400]

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    if data.get("session_id"):
        session_ids[cid] = str(data["session_id"])

    failures: List[str] = []
    if err:
        failures.append(err)

    expect_agent = case.get("expect_agent")
    actual_agent = data.get("agent_id")
    if expect_agent and actual_agent != expect_agent:
        failures.append(f"agent: 期望 {expect_agent}, 实际 {actual_agent}")

    expect_status = case.get("expect_status", "success")
    actual_status = data.get("status")
    if isinstance(expect_status, list):
        if actual_status not in expect_status:
            failures.append(f"status: 期望 {expect_status}, 实际 {actual_status}")
    elif actual_status != expect_status:
        failures.append(f"status: 期望 {expect_status}, 实际 {actual_status}")

    failed_steps = [s for s in (data.get("plan") or []) if s.get("status") == "failed"]
    if failed_steps and not case.get("allow_failed_steps"):
        failures.append(f"plan 失败步: {failed_steps}")

    failures.extend(_check_artifacts(data, case))

    tools = [str(s.get("tool")) for s in (data.get("plan") or []) if s.get("tool")]
    wl_err = _validate_tools_whitelist(actual_agent or "", tools) if tools else None
    if wl_err:
        failures.append(wl_err)

    max_ms = float(case.get("max_ms") or 180000)
    if elapsed > max_ms:
        failures.append(f"超时: {elapsed}ms > {max_ms}ms")

    if data.get("error") and actual_status not in ("success", "pending_confirm", "need_input", "pending_clarification"):
        failures.append(str(data.get("error"))[:200])

    return E2eCaseResult(
        case_id=cid,
        ok=not failures,
        tier="exec",
        message="; ".join(failures),
        detail={
            "agent_id": actual_agent,
            "status": actual_status,
            "tools": tools,
            "error": data.get("error") or err,
            "summary_zh": (data.get("summary_zh") or "")[:120],
            "artifact_keys": list((data.get("artifacts") or {}).keys()),
        },
        elapsed_ms=elapsed,
        tags=list(case.get("tags") or []),
    )


def _collect_meta() -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": os.getenv("ZHIPU_MODEL", "glm-4.5-air"),
        "llm_react": os.getenv("LLM_REACT_ENABLED", "0"),
        "llm_reflect": os.getenv("LLM_REFLECT_ENABLED", "0"),
    }
    try:
        from metaforge.orchestrator.router import ROUTER_BUILD_ID

        meta["router_build_id"] = ROUTER_BUILD_ID
    except Exception:
        pass
    return meta


def run_suite(
    tier: str,
    *,
    cases: Optional[List[Dict[str, Any]]] = None,
    run_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    react: bool = False,
    reflect: bool = False,
    verbose: bool = True,
) -> E2eReport:
    from metaforge.orchestrator.session import clear_all_sessions
    from metaforge.tools.load_all import load_all_tools

    load_all_tools()
    clear_all_sessions()
    os.environ.setdefault("SESSION_STORE", "memory")
    if tier == "exec":
        os.environ.setdefault("AGENT_E2E", "1")
        if not _env_truthy("AGENT_E2E_LITE"):
            os.environ.setdefault("AGENT_E2E_MONGO", "1")
            os.environ.setdefault("AGENT_E2E_SLOW", "1")
        _warm_e2e_app()
    _apply_llm_env(react=react, reflect=reflect)

    report = E2eReport(tier=tier, meta=_collect_meta())
    session_ids: Dict[str, str] = {}
    items = cases if cases is not None else load_cases(tier)

    for i, case in enumerate(items, 1):
        cid = case.get("id") or "?"
        skip = _should_skip_case(case, tier=tier)
        if skip:
            report.results.append(
                E2eCaseResult(
                    case_id=cid,
                    ok=True,
                    tier=tier,
                    skipped=True,
                    skip_reason=skip,
                    tags=list(case.get("tags") or []),
                )
            )
            continue

        if verbose:
            msg = (case.get("message") or case.get("intent") or "")[:40]
            print(f"[{i}/{len(items)}] {cid}: {msg}", flush=True)

        if tier == "preview":
            result = run_l2_case(case)
        else:
            if run_fn is None:
                report.results.append(
                    E2eCaseResult(
                        case_id=cid,
                        ok=False,
                        tier="exec",
                        skipped=True,
                        skip_reason="未提供 run_fn",
                        tags=list(case.get("tags") or []),
                    )
                )
                continue
            result = run_l3_case(case, run_fn=run_fn, session_ids=session_ids)

        report.results.append(result)
        if verbose:
            mark = "SKIP" if result.skipped else ("OK" if result.ok else "FAIL")
            print(f"    -> {mark} {result.elapsed_ms:.0f}ms {result.message[:80]}", flush=True)

    return report


def format_report_md(report: E2eReport) -> str:
    lines = [
        f"=== MetaForge Agent E2E ({report.tier}) ===",
        f"通过: {report.passed}  失败: {report.failed}  跳过: {report.skipped}",
        f"通过率: {report.rate() * 100:.1f}%",
        f"模型: {report.meta.get('model')}  router: {report.meta.get('router_build_id', '—')}",
        "",
    ]
    by_tag = report.by_tag()
    if by_tag:
        lines.append("## 按 Tag")
        for tag, bucket in sorted(by_tag.items()):
            total = bucket["pass"] + bucket["fail"]
            rate = (bucket["pass"] / total * 100) if total else 0.0
            lines.append(f"- {tag}: {rate:.0f}% ({bucket['pass']}/{total}), skip {bucket['skip']}")
        lines.append("")

    fails = report.failures()
    if fails:
        lines.append("## 失败明细")
        for r in fails:
            lines.append(f"### {r.case_id}")
            lines.append(f"- {r.message}")
            for k, v in (r.detail or {}).items():
                lines.append(f"- {k}: {v}")
            lines.append("")
    return "\n".join(lines)


def _tests_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "tests"


def _load_fastapi_app():
    """FastAPI 入口在 tests/main.py；pytest 会自动加 path，CLI 需显式加载。"""
    tests_dir = _tests_dir()
    if not tests_dir.is_dir():
        raise RuntimeError(f"未找到 tests 目录: {tests_dir}")
    tests_str = str(tests_dir)
    if tests_str not in sys.path:
        sys.path.insert(0, tests_str)
    return importlib.import_module("main").app


def default_run_fn(body: Dict[str, Any]) -> Dict[str, Any]:
    """每条用例独立 TestClient，减轻连续 async Mongo 导致的事件循环关闭问题。"""
    os.environ.setdefault("AGENT_E2E", "1")
    from fastapi.testclient import TestClient

    with TestClient(_load_fastapi_app()) as client:
        r = client.post("/api/orchestrator/run", json=body)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def _load_dotenv_if_present() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def main(argv: Optional[List[str]] = None) -> int:
    _load_dotenv_if_present()
    parser = argparse.ArgumentParser(description="MetaForge Agent GLM E2E 评测")
    parser.add_argument("--tier", choices=("preview", "exec"), default="preview")
    parser.add_argument("--tags", type=str, default="", help="逗号分隔 tag 过滤")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json", type=str, default="", help="JSON 报告路径")
    parser.add_argument("--react", action="store_true")
    parser.add_argument("--reflect", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)

    if args.tier == "preview":
        os.environ.setdefault("RUN_GLM_PREVIEW", "1")
    else:
        os.environ.setdefault("RUN_GLM_EXEC", "1")
        os.environ.setdefault("AGENT_E2E", "1")
        if not _env_truthy("AGENT_E2E_LITE"):
            os.environ.setdefault("AGENT_E2E_MONGO", "1")
            os.environ.setdefault("AGENT_E2E_SLOW", "1")

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] or None
    cases = load_cases(
        args.tier,
        tags=tags,
        limit=args.limit if args.limit > 0 else None,
    )

    key_err = _check_api_key()
    if key_err and not any(
        _should_skip_case(c, tier=args.tier) for c in cases[:1]
    ):
        # 若全部会 skip 则不必报错；否则检查 key
        active = [c for c in cases if not _should_skip_case(c, tier=args.tier)]
        if active and key_err:
            print(key_err, file=sys.stderr)
            print("提示: 复制 .env.example 为 .env 并填入 ZHIPU_API_KEY", file=sys.stderr)
            return 2

    run_fn = default_run_fn if args.tier == "exec" else None
    report = run_suite(
        args.tier,
        cases=cases,
        run_fn=run_fn,
        react=args.react,
        reflect=args.reflect,
        verbose=not args.quiet,
    )
    text = format_report_md(report)
    print(text)

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 已写入: {out.resolve()}")

    active = [r for r in report.results if not r.skipped]
    if not active:
        return 0
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
