import json
from pathlib import Path
from datetime import datetime
from . import state
from .config import HISTORY_FILE, set_last_model, print_warn, print_info, print_error

def save_conversation(filepath=None):
    if filepath is None:
        from . import config
        filepath = config.HISTORY_FILE
    data = {
        "model": state.current_model,
        "system_prompt": state.system_prompt,
        "auto_routing": state.auto_routing,
        "messages": state.conversation,
    }
    try:
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        if state.current_model:
            set_last_model(state.current_model)
        print_warn(f"Saved {len(state.conversation)} messages to {filepath}")
    except Exception as e:
        print_error(f"Failed to save conversation: {e}")


def load_conversation_metadata(filepath=None):
    """Inspect saved conversation metadata without modifying state.conversation."""
    if filepath is None:
        from . import config
        filepath = config.HISTORY_FILE
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {"model": None, "count": len(data), "system_prompt": None}
        elif isinstance(data, dict):
            messages = data.get("messages", [])
            sys_p = data.get("system_prompt") or data.get("state.system_prompt")
            model = data.get("model")
            return {"model": model, "count": len(messages), "system_prompt": sys_p}
    except Exception:
        pass
    return {"model": None, "count": 0, "system_prompt": None}


def load_conversation(filepath=None):
    """Explicitly restore previous conversation messages and settings into state."""
    if filepath is None:
        from . import config
        filepath = config.HISTORY_FILE
    saved_model = None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            state.conversation = data
        elif isinstance(data, dict):
            state.conversation = data.get("messages", [])
            # Support both new clean key and legacy refactored key
            sys_p = data.get("system_prompt") or data.get("state.system_prompt")
            if sys_p:
                state.system_prompt = sys_p
                print_info(f"Restored system prompt: {sys_p[:80]}...")
            state.auto_routing = data.get("auto_routing", data.get("state.auto_routing", False))
            saved_model = data.get("model")
        print_warn(f"Resumed {len(state.conversation)} previous messages")
    except FileNotFoundError:
        state.conversation = []
        print_warn("No previous conversation found.")
    except json.JSONDecodeError:
        print_error("Corrupted history file. Starting fresh.")
        state.conversation = []
    return saved_model


def export_as_markdown(filepath=None):
    if filepath is None:
        filepath = f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        if state.system_prompt:
            f.write(f"**System:**\n\n{state.system_prompt}\n\n---\n\n")
        for msg in state.conversation:
            role = msg["role"].capitalize()
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                content = " ".join(parts)
            f.write(f"**{role}:**\n\n{content}\n\n---\n\n")
    print_warn(f"Exported transcript to {filepath}")


