"""策略规划相关 Tool（导入时注册）。"""

from metaforge.tools.planning.run import register_planning_run_tool
from metaforge.tools.planning.strategy_evaluate import register_strategy_evaluate_tool
from metaforge.tools.planning.strategy_generate import register_strategy_generate_tool
from metaforge.tools.planning.strategy_validate import register_strategy_validate_tool

register_strategy_generate_tool()
register_strategy_validate_tool()
register_strategy_evaluate_tool()
register_planning_run_tool()
