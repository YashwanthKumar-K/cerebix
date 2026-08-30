import threading
import time
from contextlib import contextmanager
from .config import HAS_RICH, console

# Rotating messages shown during Phase 1 (architecture planning)
_PLAN_MESSAGES = [
    "Thinking...",
    "Brainstorming structure...",
    "Architecting your project...",
    "Designing file layout...",
    "Planning dependencies...",
    "Mapping out the codebase...",
    "Consulting the blueprint...",
    "Evaluating tech stack...",
    "Sketching the architecture...",
    "Thinking about file structure...",
]

# Rotating messages shown during Phase 2 (per-file code generation)
_CODE_MESSAGES = [
    "Writing code...",
    "Crafting functions...",
    "Building the logic...",
    "Connecting the pieces...",
    "Generating implementation...",
    "Wiring up imports...",
    "Filling in the details...",
    "Adding finishing touches...",
    "Cooking up some code...",
    "Assembling the module...",
]



@contextmanager
def _thinking_spinner(messages):
    """Context manager: shows a rotating spinner + message while waiting for an API call.

    Usage:
        with _thinking_spinner(_PLAN_MESSAGES):
            result = slow_api_call()
    """
    stop_event = threading.Event()
    start_time = time.time()
    state = {"idx": 0}

    if HAS_RICH:
        def _rotate(status_obj):
            while not stop_event.wait(0.1):  # update every 100ms for smooth timer
                elapsed = time.time() - start_time
                # rotate the text message every 2.5 seconds
                state["idx"] = int((elapsed // 2.5) % len(messages))
                msg = messages[state["idx"]]
                status_obj.update(f"[bold cyan]{msg}[/] [dim]({elapsed:.1f}s)[/]")

        with console.status(f"[bold cyan]{messages[0]}[/] [dim](0.0s)[/]", spinner="dots") as st:
            t = threading.Thread(target=_rotate, args=(st,), daemon=True)
            t.start()
            try:
                yield
            finally:
                stop_event.set()
                t.join(timeout=1)
    else:
        # Fallback: print cycling messages with carriage return
        def _rotate_plain():
            while not stop_event.wait(0.1):
                elapsed = time.time() - start_time
                state["idx"] = int((elapsed // 2.5) % len(messages))
                msg = messages[state["idx"]]
                print(f"\r  {msg} ({elapsed:.1f}s)    ", end="", flush=True)

        print(f"  {messages[0]} (0.0s)", end="", flush=True)
        t = threading.Thread(target=_rotate_plain, daemon=True)
        t.start()
        try:
            yield
        finally:
            stop_event.set()
            t.join(timeout=1)
            print()  # newline after spinner clears


