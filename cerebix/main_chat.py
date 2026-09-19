from . import state
from .config import print_error
from .routing import route_model
from .api import stream_response

def get_system_prompt(model=None):
    if state.system_prompt:
        return state.system_prompt

    name = model.get("name", "AI Assistant") if model else "AI Assistant"
    mid  = model.get("id", "") if model else ""
    id_line = f"You are {name} ({mid})" if mid else f"You are {name}"

    return (
        f"{id_line}, accessed through Cerebix — an open-source multi-model terminal client.\n"
        f"- Identify truthfully as {name}; never claim to be 'Cerebix AI'.\n"
        "- Clean markdown, labeled code blocks. Direct, no filler. State uncertainty explicitly. Short, dense answers."
    )


def ask_model(prompt, free_models=None):
    """Send a prompt to the routed model, stream the response, update history."""

    model = route_model(prompt, free_models or []) if free_models else state.current_model
    if not model:
        print_error("No model selected. Use /select to pick one.")
        return

    messages = []
    active_system = get_system_prompt(model)
    messages.append({"role": "system", "content": active_system})

    # Apply history limit to reduce token usage
    history = state.conversation
    if state.history_limit and len(history) > state.history_limit:
        history = history[-state.history_limit:]

    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model["id"],
        "messages": messages,
        "max_tokens": 4096,
    }
    content = stream_response(payload, free_models=free_models)

    if content:
        state.conversation.append({"role": "user", "content": prompt})
        state.conversation.append({"role": "assistant", "content": content})


