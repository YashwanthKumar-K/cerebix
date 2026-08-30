import json
from datetime import datetime
from . import state
from .config import HISTORY_FILE, print_warn, print_info, print_error

def save_conversation(filepath=HISTORY_FILE):
    data = {
        "model": state.current_model,
        "state.system_prompt": state.system_prompt,
        "state.auto_routing": state.auto_routing,
        "messages": state.conversation,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print_warn(f"Saved {len(state.conversation)} messages to {filepath}")


def load_conversation(filepath=HISTORY_FILE):

    saved_model = None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            state.conversation = data
        elif isinstance(data, dict):
            state.conversation = data.get("messages", [])
            sys_p = data.get("state.system_prompt")
            if sys_p:
                state.system_prompt = sys_p
                print_info(f"Restored system prompt: {sys_p[:80]}...")
            state.auto_routing = data.get("state.auto_routing", False)
            saved_model = data.get("model")
        print_warn(f"Resumed {len(state.conversation)} previous messages")
    except FileNotFoundError:
        state.conversation = []
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


