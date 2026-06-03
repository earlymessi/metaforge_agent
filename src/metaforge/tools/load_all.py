"""导入所有 Tool 子包以完成注册（API 启动时调用）。"""

from __future__ import annotations


def load_all_tools() -> None:
    import metaforge.tools.scheduling  # noqa: F401
    import metaforge.tools.material  # noqa: F401
    import metaforge.tools.delivery  # noqa: F401
    import metaforge.tools.events  # noqa: F401
    import metaforge.tools.kitting  # noqa: F401
    import metaforge.tools.compare  # noqa: F401
    import metaforge.tools.data  # noqa: F401
    import metaforge.tools.execution  # noqa: F401
    import metaforge.tools.memory  # noqa: F401
