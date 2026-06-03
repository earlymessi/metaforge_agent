"""计划管理意图解析：LLM 主路径（plans_intent prompt）+ 离线规则兜底。

- ``parse_plan_intent``：整句精确匹配，仅用于路由 guard 与 ``LLM_ENABLED=0`` 时快速命中。
- ``rule_fallback_plan_intent``：LLM 不可用或失败时的保守短语兜底。
- 自然语言理解与 action 判别以 ``orchestrator/llm/prompts.plans_intent_*`` 为准。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

PREFIX = re.compile(r"^(?:请|帮我|麻烦|我想|我要)?\s*")

# 增/改/查完成后跳转智能排程；删除与纯列表不跳转
NAVIGATE_APS_ACTIONS = frozenset(
    {"create", "view", "bind", "rename", "duplicate", "update_status", "goto_aps"}
)


def should_navigate_aps(action: str) -> bool:
    return (action or "") in NAVIGATE_APS_ACTIONS


def _with_nav(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if should_navigate_aps(action):
        payload["navigate_aps"] = True
    return payload


def is_plans_management_message(message: str) -> bool:
    """仅当第一层精确规则命中计划库操作时返回 True（供路由 guard / 排程避让）。"""
    return parse_plan_intent(message) is not None


def rule_fallback_plan_intent(message: str, *, llm_error: str = "") -> Dict[str, Any]:
    """第三层：LLM 不可用或失败时的保守兜底。

    先复用 ``parse_plan_intent`` 整句规则；仅对非整句口语保留少量 search 兜底。
    """
    parsed = parse_plan_intent(message)
    if parsed is not None:
        out = dict(parsed)
        if llm_error:
            out["llm_error"] = llm_error[:300]
        return out

    raw = (message or "").strip()
    if not raw:
        return {"action": "list"}
    t = PREFIX.sub("", raw).strip()

    if re.search(r"(?:新建|创建|添加)(?:一个|新的)?(?:计划|订单)", t, re.I):
        m = re.search(
            r"(?:名为|叫做|叫|名称[是为]|名字[是为])\s*[「\"'『]?([^」\"'\s，,。.!?]+)",
            t,
            re.I,
        )
        return _with_nav("create", {"action": "create", "plan_name": (m.group(1) if m else "").strip()})

    if re.search(r"(?:删除|删掉|移除)(?:计划|订单)", t, re.I):
        m = re.search(
            r"(?:删除|删掉|移除)(?:计划|订单)?\s*[「\"'『]?([^」\"'\s，,。.!?]+)",
            t,
            re.I,
        )
        return {"action": "delete", "query": (m.group(1) if m else "").strip()}

    if re.search(r"(?:列出|显示|刷新|查看所有|查看全部)(?:计划|订单)", t, re.I):
        return {"action": "list"}

    if re.search(r"(?:加载|打开|绑定|使用|载入)(?:计划|订单)", t, re.I):
        m = re.search(
            r"(?:加载|打开|绑定|使用|载入)(?:计划|订单)?\s*[「\"'『]?([^」\"'\s，,。.!?]+)",
            t,
            re.I,
        )
        return _with_nav(
            "bind",
            {"action": "bind", "query": (m.group(1) if m else "").strip()},
        )

    out: Dict[str, Any] = {"action": "list"}
    if llm_error:
        out["llm_error"] = llm_error[:300]
    return out


def parse_plan_intent(message: str) -> Optional[Dict[str, Any]]:
    """第一层精确规则：整句匹配成功才返回 intent，否则 None（交给 LLM）。"""
    raw = (message or "").strip()
    if not raw:
        return {"action": "list"}
    t = PREFIX.sub("", raw).strip()

    m = re.match(
        r"^(?:新建|创建|添加)(?:一个)?(?:名为|叫做|叫|名称[是为]|名字[是为])?\s*"
        r"[「\"'『]?([^」\"'\s，,。.!?]+)[」\"'『]?\s*(?:的)?(?:计划|订单|工单计划)\s*[。.!?]*$",
        t,
        re.I,
    )
    if m:
        return _with_nav("create", {"action": "create", "plan_name": (m.group(1) or "").strip()})

    m = re.match(
        r"^(?:新建|创建|添加)(?:一个)?(?:新的)?(?:计划|订单|工单计划)\s*"
        r"(?:[，,\s]*(?:叫|名为))?\s*[「\"'『]?([^」\"'\s，,。.!?]+)?[」\"'『]?\s*[。.!?]*$",
        t,
        re.I,
    )
    if m:
        return _with_nav("create", {"action": "create", "plan_name": (m.group(1) or "").strip()})

    if re.match(r"^(?:列出|显示|刷新)(?:所有|全部)?(?:计划|订单)(?:列表)?\s*[。.!?]*$", t, re.I):
        return {"action": "list"}

    m = re.match(
        r"^(?:查看|看一下|看看|查询)(?:一下)?计划\s*[「\"'『]?([^」\"'\s，,。.!?]+)[」\"'『]?\s*[。.!?]*$",
        t,
        re.I,
    )
    if m:
        q = (m.group(1) or "").strip()
        if q not in ("列表", "所有", "全部"):
            return _with_nav("view", {"action": "view", "query": q})

    m = re.match(
        r"^(?:查看|看一下|看看|查询)(?:一下)?[「\"'『]?([^」\"'\s，,。.!?]+)[」\"'『]?\s*(?:计划|订单)\s*[。.!?]*$",
        t,
        re.I,
    )
    if m:
        q = (m.group(1) or "").strip()
        if q not in ("列表", "所有", "全部"):
            return _with_nav("view", {"action": "view", "query": q})

    if re.match(r"^(?:查看|看一下|看看|查询)(?:一下)?(?:所有|全部)?(?:计划|订单)(?:列表)?\s*[。.!?]*$", t, re.I):
        return {"action": "list"}

    m = re.match(
        r"^(?:复制|拷贝|克隆)(?:计划|订单)?\s*[「\"'『]?(.+?)[」\"'『]?\s*(?:为|成|到)\s*"
        r"[「\"'『]?([^」\"'\s，,。.!?]+)[」\"'『]?\s*[。.!?]*$",
        t,
        re.I,
    )
    if m:
        return _with_nav(
            "duplicate",
            {
                "action": "duplicate",
                "query": (m.group(1) or "").strip(),
                "new_name": (m.group(2) or "").strip(),
            },
        )

    m = re.match(
        r"^(?:重命名|改名)(?:计划|订单)?\s*[「\"'『]?([^」\"'\s，,。.!?]+)[」\"'『]?\s*"
        r"(?:为|成|叫)\s*[「\"'『]?([^」\"'\s，,。.!?]+)[」\"'『]?\s*[。.!?]*$",
        t,
        re.I,
    )
    if m:
        return _with_nav(
            "rename",
            {
                "action": "rename",
                "query": (m.group(1) or "").strip(),
                "new_name": (m.group(2) or "").strip(),
            },
        )

    m = re.match(
        r"^(?:标记|设为|更新)(?:计划|订单)?\s*[「\"'『]?([^」\"'\s，,。.!?]+)[」\"'『]?\s*"
        r"(?:为|成)?\s*(待排|已完成|归档|pending|done|archived)\s*[。.!?]*$",
        t,
        re.I,
    )
    if m:
        st = (m.group(2) or "").strip().lower()
        status_map = {"待排": "pending", "已完成": "done", "归档": "archived"}
        return _with_nav(
            "update_status",
            {
                "action": "update_status",
                "query": (m.group(1) or "").strip(),
                "status": status_map.get(st, st),
            },
        )

    m = re.match(
        r"^(?:删除|删掉|移除)(?:计划|订单)?\s*[「\"'『]?([^」\"'\s，,。.!?]+)[」\"'『]?\s*[。.!?]*$",
        t,
        re.I,
    )
    if m:
        return {"action": "delete", "query": (m.group(1) or "").strip()}

    m = re.match(
        r"^(?:加载|打开|选择|切换|绑定|使用|载入)(?:计划|订单|工单)?\s*[：:\s]*"
        r"[「\"'『]?([^」\"'\s，,。.!?]+)[」\"'『]?\s*[。.!?]*$",
        t,
        re.I,
    )
    if m:
        return _with_nav("bind", {"action": "bind", "query": (m.group(1) or "").strip()})

    if re.match(r"^(?:打开|去|进入|跳转|转到)(?:智能)?排程(?:中心|页面)?\s*[。.!?]*$", t, re.I):
        return _with_nav("goto_aps", {"action": "goto_aps"})

    if re.match(r"^(?:解绑|清除|取消)(?:当前)?(?:计划|订单|绑定)\s*[。.!?]*$", t, re.I):
        return {"action": "clear"}

    return None
