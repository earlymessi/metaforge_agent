import os
import sys
import tempfile

TOOLS = r"C:\Users\liu\.codex\plugins\cache\openai-primary-runtime\presentations\26.819.11345\skills\presentations\container_tools"
FIXED = r"D:\Desktop\metaforge\.tmp\metaforge_agent_ppt_20260823\qa_fixed"

os.makedirs(FIXED, exist_ok=True)
sys.path.insert(0, TOOLS)
tempfile.mkdtemp = lambda: FIXED

import slides_test

slides_test.main()
