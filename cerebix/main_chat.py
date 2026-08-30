from . import state
from .config import print_error
from .routing import route_model
from .api import stream_response

def ask_model(prompt, free_models=None):
    """Send a prompt to the routed model, stream the response, update history."""


    model = route_model(prompt, free_models or []) if free_models else state.current_model
    if not model:
        print_error("No model selected. Use /select to pick one.")
        return

    messages = []
    if state.system_prompt:
        messages.append({"role": "system", "content": state.system_prompt})
    messages.extend(state.conversation)
    messages.append({"role": "user", "content": prompt})

    payload = {"model": model["id"], "messages": messages}
    content = stream_response(payload)

    if content:
        state.conversation.append({"role": "user", "content": prompt})
        state.conversation.append({"role": "assistant", "content": content})


