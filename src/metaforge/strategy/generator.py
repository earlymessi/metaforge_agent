from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple

from metaforge.agent.scheduling_agent import _STRATEGY_NL
from metaforge.strategy.guardrails import validate_strategy
from metaforge.strategy.models import Constraint, SchedulingStrategy
from metaforge.strategy.presets import strategy_from_preset

_CHANGEOVER_HINTS = ("减少换型", "少换型", "换型", "setup", "changeover")
_ON_TIME_RE = re.compile(r"保证(?:客户)?([A-Za-z0-9_\-\u4e00-\u9fff]+)按期")
_CUSTOMER_RE = re.compile(r"客户([A-Za-z0-9_\-\u4e00-\u9fff]+)")


def _job_ref(job: Any) -> Optional[str]:
    if isinstance(job, str):
        return job
    if not isinstance(job, dict):
        return str(job)
    for key in ("job_id", "id", "name"):
        value = job.get(key)
        if value is not None and value != "":
            return str(value)
    return None


def _job_customer(job: Any) -> Optional[str]:
    if isinstance(job, dict):
        customer = job.get("customer")
        if customer is not None and customer != "":
            return str(customer)
    return None


def _match_preset(user_goal: str) -> str:
    text = user_goal or ""
    best_id = "balanced"
    best_score = 0
    for preset_id, keywords in _STRATEGY_NL.items():
        for keyword in keywords:
            if keyword.lower() in text.lower() or keyword in text:
                if len(keyword) > best_score:
                    best_score = len(keyword)
                    best_id = preset_id
    return best_id


def _extract_critical_tokens(user_goal: str) -> List[str]:
    tokens: List[str] = []
    for pattern in (_ON_TIME_RE, _CUSTOMER_RE):
        for match in pattern.finditer(user_goal or ""):
            token = match.group(1).strip()
            if token and token not in tokens:
                tokens.append(token)
    return tokens


def _resolve_critical_orders(tokens: List[str], jobs: Iterable[Any]) -> List[str]:
    resolved: List[str] = []
    for token in tokens:
        for job in jobs or []:
            job_id = _job_ref(job)
            customer = _job_customer(job)
            if job_id == token or customer == token:
                if job_id and job_id not in resolved:
                    resolved.append(job_id)
    return resolved


def _build_rule_fallback_strategy(
    *,
    user_goal: str,
    jobs: Iterable[Any],
) -> SchedulingStrategy:
    preset_id = _match_preset(user_goal)
    strategy = strategy_from_preset(preset_id)
    strategy.generated_by = "rule_fallback"
    strategy.explanation = f"Rule fallback matched preset {preset_id!r} from natural language."

    critical_tokens = _extract_critical_tokens(user_goal)
    critical_orders = _resolve_critical_orders(critical_tokens, jobs)
    strategy.critical_orders = critical_orders

    hard_constraints = list(strategy.hard_constraints)
    for job_id in critical_orders:
        due = None
        for job in jobs or []:
            if _job_ref(job) == job_id and isinstance(job, dict):
                due = job.get("due_date", job.get("due"))
                break
        params: Dict[str, Any] = {"job_id": job_id}
        if due is not None:
            params["due"] = due
        hard_constraints.append(Constraint(type="order_on_time", params=params))
    strategy.hard_constraints = hard_constraints

    text = user_goal or ""
    if any(h in text for h in _CHANGEOVER_HINTS):
        strategy.soft_constraints = list(strategy.soft_constraints) + [
            Constraint(type="reduce_changeover", params={})
        ]

    return strategy


def _try_llm_strategy(
    *,
    llm_client: Any,
    context: Dict[str, Any],
    user_goal: str,
) -> Tuple[Optional[SchedulingStrategy], Dict[str, Any]]:
    meta: Dict[str, Any] = {"generated_by": "llm", "fallback": False}
    if llm_client is None:
        return None, meta

    complete = getattr(llm_client, "complete_json", None) or getattr(llm_client, "complete", None)
    if not callable(complete):
        meta["llm_error"] = "llm_client has no complete_json/complete method"
        return None, meta

    prompt = {
        "task": "generate_scheduling_strategy",
        "user_goal": user_goal,
        "context": context,
    }
    last_error = "LLM returned no usable strategy"

    for attempt in range(3):
        try:
            if getattr(llm_client, "complete_json", None):
                raw = llm_client.complete_json(prompt, attempt=attempt)
            else:
                raw_text = llm_client.complete(json.dumps(prompt, ensure_ascii=False), attempt=attempt)
                raw = json.loads(raw_text)
            strategy = SchedulingStrategy.from_dict(raw)
            strategy.generated_by = "llm"
            meta["attempts"] = attempt + 1
            return strategy, meta
        except Exception as exc:  # noqa: BLE001 - surface as repair/fallback signal
            last_error = str(exc)
            meta["llm_error"] = last_error
            meta["attempts"] = attempt + 1

    return None, meta


def _constraint_from_raw(raw: Dict[str, Any]) -> Constraint:
    ctype = str(raw.get("type") or "")
    penalty = raw.get("penalty")
    params = {k: v for k, v in raw.items() if k not in ("type", "penalty")}
    return Constraint(type=ctype, params=params, penalty=penalty)


def merge_collab_analyses(
    strategy: SchedulingStrategy,
    *,
    order_analysis: Optional[Dict[str, Any]] = None,
    constraint_analysis: Optional[Dict[str, Any]] = None,
    resource_analysis: Optional[Dict[str, Any]] = None,
) -> SchedulingStrategy:
    """Merge Order/Constraint/Resource analysis artifacts into a strategy."""
    order_analysis = order_analysis or {}
    constraint_analysis = constraint_analysis or {}
    resource_analysis = resource_analysis or {}

    critical = list(strategy.critical_orders)
    for jid in order_analysis.get("critical_orders") or []:
        sid = str(jid)
        if sid and sid not in critical:
            critical.append(sid)
    strategy.critical_orders = critical

    hard = list(strategy.hard_constraints)
    soft = list(strategy.soft_constraints)
    seen_hard = {(c.type, tuple(sorted((c.params or {}).items()))) for c in hard}
    seen_soft = {(c.type, tuple(sorted((c.params or {}).items()))) for c in soft}

    for raw in constraint_analysis.get("hard_constraints") or []:
        if not isinstance(raw, dict):
            continue
        c = _constraint_from_raw(raw)
        key = (c.type, tuple(sorted((c.params or {}).items())))
        if key not in seen_hard:
            hard.append(c)
            seen_hard.add(key)

    for raw in constraint_analysis.get("soft_constraints") or []:
        if not isinstance(raw, dict):
            continue
        c = _constraint_from_raw(raw)
        key = (c.type, tuple(sorted((c.params or {}).items())))
        if key not in seen_soft:
            soft.append(c)
            seen_soft.add(key)

    oot_jobs = {
        str(c.params.get("job_id"))
        for c in hard
        if c.type == "order_on_time" and c.params.get("job_id") is not None
    }
    for jid in critical:
        if jid not in oot_jobs:
            hard.append(Constraint(type="order_on_time", params={"job_id": jid}))
            oot_jobs.add(jid)

    strategy.hard_constraints = hard
    strategy.soft_constraints = soft

    bottlenecks = resource_analysis.get("bottleneck_machines") or []
    if bottlenecks:
        prefs = dict(strategy.machine_preferences or {})
        prefs["bottlenecks"] = list(bottlenecks)
        strategy.machine_preferences = prefs

    provenance = dict(strategy.provenance or {})
    provenance["collab_analyses"] = True
    strategy.provenance = provenance
    return strategy


def generate_strategy(
    *,
    user_goal: str,
    jobs: Iterable[Any],
    machines: Iterable[Any],
    llm_client: Any = None,
    workers: Optional[Iterable[Any]] = None,
    tools: Optional[Iterable[Any]] = None,
    gantt_data: Any = None,
    bom: Any = None,
    allow_simulated: bool = True,
    order_analysis: Optional[Dict[str, Any]] = None,
    constraint_analysis: Optional[Dict[str, Any]] = None,
    resource_analysis: Optional[Dict[str, Any]] = None,
) -> Tuple[SchedulingStrategy, Dict[str, Any]]:
    from metaforge.strategy.context_builder import build_for_strategy_generation

    context = build_for_strategy_generation(
        user_goal=user_goal,
        jobs=jobs,
        machines=machines,
        gantt_data=gantt_data,
        bom=bom,
        order_analysis=order_analysis,
        constraint_analysis=constraint_analysis,
        resource_analysis=resource_analysis,
    )

    meta: Dict[str, Any] = {"context": context}

    strategy, llm_meta = _try_llm_strategy(
        llm_client=llm_client,
        context=context,
        user_goal=user_goal,
    )
    meta.update(llm_meta)

    if strategy is None:
        strategy = _build_rule_fallback_strategy(user_goal=user_goal, jobs=jobs)
        meta["fallback"] = True
        meta["generated_by"] = "rule_fallback"
    else:
        meta.setdefault("fallback", False)
        meta["generated_by"] = "llm"

        llm_ok, llm_errors, _ = validate_strategy(
            strategy,
            jobs=jobs,
            machines=machines,
            workers=workers,
            tools=tools,
            allow_simulated=allow_simulated,
        )
        if not llm_ok:
            meta["llm_validation_failed"] = True
            meta["validation_errors"] = llm_errors
            strategy = _build_rule_fallback_strategy(user_goal=user_goal, jobs=jobs)
            meta["fallback"] = True
            meta["generated_by"] = "rule_fallback"

    if order_analysis or constraint_analysis or resource_analysis:
        strategy = merge_collab_analyses(
            strategy,
            order_analysis=order_analysis,
            constraint_analysis=constraint_analysis,
            resource_analysis=resource_analysis,
        )
        meta["merged_collab_analyses"] = True

    ok, errors, fixed = validate_strategy(
        strategy,
        jobs=jobs,
        machines=machines,
        workers=workers,
        tools=tools,
        allow_simulated=allow_simulated,
    )
    meta["validation_ok"] = ok
    if errors and not meta.get("llm_validation_failed"):
        meta["validation_errors"] = errors

    return deepcopy(fixed), meta
