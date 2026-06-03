"""排程相关 Tool（导入时注册）。"""

from metaforge.tools.scheduling.ask_clarification import register_ask_clarification_tool
from metaforge.tools.scheduling.list_catalog import register_scheduling_list_catalog_tool
from metaforge.tools.scheduling.parse_intent import register_parse_intent_tool
from metaforge.tools.scheduling.run import register_scheduling_run_tool

register_parse_intent_tool()
register_scheduling_run_tool()
register_scheduling_list_catalog_tool()
register_ask_clarification_tool()
