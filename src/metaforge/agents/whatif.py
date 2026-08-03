"""whatif 业务 Agent — 已由 WhatifCollabBridge + whatif_collab 接管。"""

from metaforge.agents.whatif_collab_bridge import WhatifCollabBridge
from metaforge.whatif_collab.plan_steps import build_variants_from_params

__all__ = ["WhatifCollabBridge", "build_variants_from_params"]
