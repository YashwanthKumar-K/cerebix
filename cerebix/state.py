
conversation = []
current_model = None
system_prompt = None
auto_routing = False
_scorecard = {}
CATEGORIES = ["code", "math", "creative", "reasoning", "documentation", "general"]
ssl_verify = True
draft_prompt = None
failed_models = set()
render_mode = "panel"

# Agent mode
history_limit = None        # None = keep all turns; int = keep last N messages
workspace_root = None       # None = cwd; str = absolute path to sandbox root
allow_bash = False          # Toggle via /allow on|off
max_tool_turns = 5          # Max tool iterations per agent invocation
