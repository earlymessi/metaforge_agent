"""plans 业务 Agent — 计划/订单库管理（MongoDB CRUD）。"""



from __future__ import annotations



from typing import List, Optional



from metaforge.agents.base import AgentRequest, AgentResponse, BaseAgent, PlanStep

from metaforge.plans.resolve_intent import intent_to_plan_steps, resolve_plan_intent





def _format_active_plan_summary(active: dict, intent: Optional[dict]) -> str:

    name = active.get("plan_name") or "未命名"

    n = active.get("job_count", 0)

    parts = [f"计划「{name}」", f"{n} 个工单"]

    st = active.get("plan_status")

    if st:

        st_zh = {"pending": "待排程", "done": "已完成", "scheduled": "已排程", "archived": "已归档"}.get(

            st, st

        )

        parts.append(f"状态：{st_zh}")

    if active.get("has_schedule"):

        parts.append("已有排程快照")

    action = (intent or {}).get("action")
    nav_tail = "。正在打开排程中心，可说「按交期优先排产」继续。"
    if action == "view":
        head = "已找到并绑定：" if n else "已找到计划（暂无工单）："
        return head + "，".join(parts) + nav_tail
    if action in ("create", "bind", "rename", "duplicate", "update_status"):
        verb = {
            "create": "已新建",
            "bind": "已加载",
            "rename": "已重命名",
            "duplicate": "已复制",
            "update_status": "已更新状态",
        }.get(action, "已处理")
        return verb + " " + "，".join(parts) + nav_tail
    return "已处理 " + "，".join(parts) + "。"





class PlansAgentRunner(BaseAgent):

    agent_id = "plans"

    name_zh = "计划管理"

    allowed_tools = [

        "data.list_plans",

        "data.create_plan",

        "data.delete_plan",

        "data.bind_plan",

        "data.rename_plan",

        "data.duplicate_plan",

        "data.update_status",

    ]



    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:

        intent, planner = resolve_plan_intent(request.message, params=request.params)

        self._resolved_intent = intent

        self._plan_planner = planner

        return intent_to_plan_steps(intent)



    def finalize(self, request: AgentRequest, ctx, plan_log) -> AgentResponse:

        intent = getattr(self, "_resolved_intent", None)

        ui = (ctx.artifacts or {}).get("ui_action")



        if intent and intent.get("action") == "clear":

            return AgentResponse(

                status="success",

                agent_id=self.agent_id,

                summary_zh="已请求解除绑定（请在前端清除当前计划选择）。",

                plan=plan_log,

                artifacts=dict(ctx.artifacts),

                plan_planner=getattr(self, "_plan_planner", "rule"),

            )



        if intent and intent.get("action") == "goto_aps":

            ctx.artifacts["ui_action"] = {"type": "navigate", "path": "/aps", "reason": "打开排程"}

            ui = ctx.artifacts["ui_action"]



        active = (ctx.artifacts or {}).get("active_plan")

        plan_list = (ctx.artifacts or {}).get("plan_list")



        if active:
            summary = _format_active_plan_summary(active, intent)
        elif plan_list is not None:

            if not plan_list:

                summary = "数据库中暂无计划。可说「新建计划叫 XXX」创建。"

            else:

                lines = [f"· {p.get('plan_name')}（{p.get('job_count', 0)} 工单）" for p in plan_list[:12]]

                extra = f"\n共 {len(plan_list)} 条。" if len(plan_list) > 12 else ""

                summary = "计划列表：\n" + "\n".join(lines) + extra

        else:

            summary = "计划管理操作已完成。"



        return AgentResponse(

            status="success",

            agent_id=self.agent_id,

            summary_zh=summary,

            plan=plan_log,

            artifacts=dict(ctx.artifacts),

            plan_planner=getattr(self, "_plan_planner", "rule"),

            ui_action=ui,

        )


