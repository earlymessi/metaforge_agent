"""kitting 业务 Agent — 已由 KittingCollabBridge + kitting_collab 接管。

历史 ``KittingAgentRunner``（BaseAgent 规则/LLM plan）已删除。
入口：``orchestrator.router.get_agent("kitting")`` → ``KittingCollabBridge``。
"""

from metaforge.agents.kitting_collab_bridge import KittingCollabBridge

__all__ = ["KittingCollabBridge"]
