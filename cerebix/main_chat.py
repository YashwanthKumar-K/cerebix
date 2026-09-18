from . import state
from .config import print_error
from .routing import route_model
from .api import stream_response

def get_system_prompt(model=None):
    """Build an authentic system prompt that preserves technical quality without faking model identity."""
    if state.system_prompt:
        return state.system_prompt

    model_name = model.get("name", "AI Assistant") if model else "AI Assistant"
    model_id = model.get("id", "") if model else ""

    id_line = f"You are {model_name}"
    if model_id:
        id_line += f" ({model_id})"
    id_line += ", accessed through Cerebix — an open-source multi-model terminal client."

    return (
        f"{id_line}\n"
        f"- If asked about your identity or which model you are, truthfully identify yourself as {model_name}.\n"
        "- Do not claim to be 'Cerebix AI' or claim that Cerebix is your creator or proprietary infrastructure; Cerebix is simply the terminal client.\n"
        "- Respond in clean markdown with proper code blocks labeled by language.\n"
        "- Be direct. Avoid conversational filler phrases like \"Great question!\", \"Certainly!\", or \"Sure, I can help with that!\".\n"
        "- If you are unsure about something or if information is missing, state it explicitly rather than guessing.\n"
        "- Prefer short, dense explanations over long verbose ones."
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
    messages.extend(state.conversation)
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


