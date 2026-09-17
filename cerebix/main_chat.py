from . import state
from .config import print_error
from .routing import route_model
from .api import stream_response

DEFAULT_SYSTEM = """You are Cerebix AI — a precise, senior-level software engineer and technical analyst.
- Respond in clean markdown with proper code blocks labeled by language.
- Be direct. Avoid conversational filler phrases like "Great question!", "Certainly!", or "Sure, I can help with that!".
- If you are unsure about something or if information is missing, state it explicitly rather than guessing.
- Prefer short, dense explanations over long verbose ones."""


def ask_model(prompt, free_models=None):
    """Send a prompt to the routed model, stream the response, update history."""

    model = route_model(prompt, free_models or []) if free_models else state.current_model
    if not model:
        print_error("No model selected. Use /select to pick one.")
        return

    messages = []
    active_system = state.system_prompt if state.system_prompt else DEFAULT_SYSTEM
    messages.append({"role": "system", "content": active_system})
    messages.extend(state.conversation)
    messages.append({"role": "user", "content": prompt})

    payload = {"model": model["id"], "messages": messages}
    content = stream_response(payload, free_models=free_models)

    if content:
        state.conversation.append({"role": "user", "content": prompt})
        state.conversation.append({"role": "assistant", "content": content})


