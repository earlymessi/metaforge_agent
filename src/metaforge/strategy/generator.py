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
) -> Tuple[SchedulingStrategy, Dict[str, Any]]:
    from metaforge.strategy.context_builder import build_for_strategy_generation

    context = build_for_strategy_generation(
        user_goal=user_goal,
        jobs=jobs,
        machines=machines,
        gantt_data=gantt_data,
        bom=bom,
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
