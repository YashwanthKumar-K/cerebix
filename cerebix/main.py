import os
import shlex
import sys
if True:
    try:
        from rich.table import Table
        from rich import box
    except ImportError:
        pass

# Interactive autocomplete for slash commands
_HAS_PROMPT_TOOLKIT = False
try:
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import WordCompleter, Completer, Completion
    from prompt_toolkit.formatted_text import HTML
    _HAS_PROMPT_TOOLKIT = True
except ImportError:
    pass

from . import state
from .config import (
    check_api_key,
    print_info,
    print_error,
    print_warn,
    print_success,
    get_ssl_verify,
    set_ssl_verify,
    get_render_mode,
    set_render_mode,
    get_last_model,
    set_last_model,
    HAS_RICH,
    console,
    Fore,
    Style,
    CHARS_PER_TOKEN,
)
from .ui import show_banner, show_help, select_startup_mode
from .scorecard import scorecard_load, scorecard_display, scorecard_record
from .persistence import (
    load_conversation,
    save_conversation,
    load_conversation_metadata,
    export_as_markdown,
)
from .models import get_free_models, display_model_table, choose_model, format_ctx
from .main_chat import ask_model
from .routing import classify_prompt
from .debate import run_debate
from .collab import run_collab
from .consensus import run_consensus
from .fanout import fan_out
from .build import run_project_build
from .context import load_file_as_prompt, load_project_as_prompt
from .utils import save_code_interactive
from .spinner import _thinking_spinner

# Command registry: (command, description, usage_hint)
COMMAND_REGISTRY = [
    ("/help",      "Show all commands",              ""),
    ("/auto",      "Toggle Smart Auto-Routing",      ""),
    ("/render",    "Toggle panel vs stream display",  ""),
    ("/ssl",       "Toggle SSL verify (WiFi/proxies)",""),
    ("/select",    "Switch active model",             ""),
    ("/models",    "List all free models",            ""),
    ("/debate",    "AI vs AI multi-round debate",     "<topic>"),
    ("/collab",    "Critic-Refiner collaborative loop","<topic> [--rounds N] [--threshold N] [--swap]"),
    ("/consensus", "Multi-model jury vote",           "<prompt>"),
    ("/fanout",    "Query models in parallel",        "<prompt>"),
    ("/build",     "Generate a full project",         "<description>"),
    ("/file",      "Send a file for review",          "<filepath>"),
    ("/project",   "Send an entire folder",           "<folder>"),
    ("/savecode",  "Extract code blocks to disk",     ""),
    ("/system",    "Set a persona/system prompt",     "<text>"),
    ("/rate",      "Rate last response (1-10)",       "<1-10>"),
    ("/scores",    "View model scorecard",            ""),
    ("/tokens",    "Show token usage",                ""),
    ("/save",      "Save conversation",               ""),
    ("/load",      "Load previous conversation",      ""),
    ("/export",    "Export as markdown",               ""),
    ("/clear",     "Clear conversation",              ""),
    ("/history",   "Set history limit (turns kept)",   "<N>"),
    ("/workspace", "Set workspace root for tools",     "<path>"),
    ("/allow",     "Toggle bash tool on/off",          "<on|off>"),
    ("/exit",      "Save & exit",                     ""),
]

if _HAS_PROMPT_TOOLKIT:
    class _CerebixCompleter(Completer):
        """Show command suggestions with descriptions as user types."""
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor.lstrip()
            if not text.startswith("/"):
                return
            for cmd, desc, hint in COMMAND_REGISTRY:
                if cmd.startswith(text):
                    display_text = f"{cmd:14s} {desc}"
                    yield Completion(cmd, start_position=-len(text), display=display_text)

    _completer = _CerebixCompleter()


def _get_input():
    """Get user input with autocomplete if prompt_toolkit is available."""
    if _HAS_PROMPT_TOOLKIT:
        try:
            return pt_prompt(
                "\nYou: ",
                completer=_completer,
                complete_while_typing=True,
            )
        except (EOFError, KeyboardInterrupt):
            raise
    elif HAS_RICH:
        return console.input("\n[bold green]You:[/] ")
    else:
        return input(f"\n{Fore.GREEN}You:{Style.RESET_ALL} ")

def main():

    
    check_api_key()

    show_banner()
    scorecard_load()
    history_meta = load_conversation_metadata()
    saved_model = get_last_model() or history_meta.get("model")
    history_count = history_meta.get("count", 0)

    # Fetch models
    with _thinking_spinner(["Connecting to OpenRouter...", "Fetching free models..."]):
        free_models = get_free_models()
    if not free_models:
        print_error("No free models found. Check your API key.")
        return

    # Startup mode selection (clean fresh session by default, explicit resume option if history exists)
    select_startup_mode(free_models, saved_model=saved_model, history_count=history_count)
    if state.current_model:
        set_last_model(state.current_model)

    # Main loop
    while True:
        try:
            if getattr(state, "draft_prompt", None):
                draft = state.draft_prompt
                state.draft_prompt = None
                print_info(f"\n[Saved Draft Restored]: {draft[:80]}...")
                try:
                    send_draft = input("Send this prompt now? (y/n) [default: y]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    send_draft = "n"
                if send_draft in ("", "y", "yes"):
                    ask_model(draft, free_models)
                    continue

            user_input = _get_input()

            if not user_input.strip():
                continue

            if not user_input.startswith("/"):
                ask_model(user_input, free_models)
                continue

            # ---- Commands ----
            try:
                parts = shlex.split(user_input)
            except ValueError:
                parts = user_input.split()
            cmd = parts[0].lower()

            # ---- Help ----
            if cmd == "/help":
                show_help()

            # ---- SSL Verification Toggle ----
            elif cmd == "/ssl":
                curr = get_ssl_verify()
                new_state = not curr
                set_ssl_verify(new_state, persist=True)
                if new_state:
                    print_success("SSL verification ENABLED (Strict secure mode).")
                else:
                    print_warn("SSL verification DISABLED (Bypassing checks for captive portals/proxies).")

            # ---- Render Mode Toggle (panel vs stream) ----
            elif cmd in ("/render", "/stream"):
                curr = get_render_mode()
                new_mode = "stream" if curr == "panel" else "panel"
                set_render_mode(new_mode, persist=True)
                if new_mode == "stream":
                    print_info("Render mode set to [bold cyan]stream[/] — Live tokens stream directly to terminal (no final duplicate panel).")
                else:
                    print_info("Render mode set to [bold green]panel[/] — Clean markdown panel rendered once upon completion.")

            # ---- System prompt ----
            elif cmd == "/system":
                if len(parts) < 2:
                    if state.system_prompt:
                        print_info(f"Current: {state.system_prompt}")
                        if input("Clear it? (y/n): ").strip().lower() == "y":
                            state.system_prompt = None
                            print_success("System prompt cleared.")
                    else:
                        print_warn("No system prompt set. Usage: /system <persona>")
                else:
                    state.system_prompt = " ".join(parts[1:])
                    print_success(f"System prompt set: {state.system_prompt}")

            # ---- Auto-routing ----
            elif cmd == "/auto":
                state.auto_routing = not state.auto_routing
                if state.auto_routing:
                    print_success("Auto-routing ON — Cerebix picks the best model per task type")
                else:
                    print_warn(f"Auto-routing OFF — using {state.current_model['name']}")

            # ---- Scores & Rating ----
            elif cmd == "/scores":
                scorecard_display()
                
            elif cmd == "/rate":
                if len(parts) < 2 or not parts[1].isdigit():
                    print_error("Usage: /rate <1-10>")
                elif not state.conversation or state.conversation[-1]["role"] != "assistant":
                    print_warn("Nothing to rate. Ask the model a question first.")
                else:
                    score = int(parts[1])
                    if not 1 <= score <= 10:
                        print_error("Score must be between 1 and 10.")
                    else:
                        # Go backwards to find the last user prompt
                        last_prompt = ""
                        for msg in reversed(state.conversation):
                            if msg["role"] == "user":
                                last_prompt = msg["content"]
                                break
                        
                        category = classify_prompt(last_prompt)
                        scorecard_record(state.current_model["id"], category, score)
                        print_success(f"Recorded score {score}/10 for {state.current_model['name']} in category '{category}'!")

            # ---- Debate ----
            elif cmd == "/debate":
                if len(parts) < 2:
                    print_error("Usage: /debate <topic> [--style standard|savage|dramatic|academic] [--rounds 2-4]")
                else:
                    run_debate(" ".join(parts[1:]), free_models)

            # ---- Collab ----
            elif cmd == "/collab":
                if len(parts) < 2:
                    print_error("Usage: /collab <topic> [--rounds N] [--threshold N] [--swap]")
                else:
                    run_collab(" ".join(parts[1:]), free_models)

            # ---- Consensus ----
            elif cmd == "/consensus":
                if len(parts) < 2:
                    print_error("Usage: /consensus <prompt>")
                else:
                    run_consensus(" ".join(parts[1:]), free_models)

            # ---- Fan-out ----
            elif cmd == "/fanout":
                if len(parts) < 2:
                    print_error("Usage: /fanout <prompt>")
                else:
                    fan_out(" ".join(parts[1:]), free_models)

            # ---- Project Build ----
            elif cmd == "/build":
                run_project_build(" ".join(parts[1:]), free_models)

            # ---- File ----
            elif cmd == "/file":
                if len(parts) < 2:
                    print_error("Usage: /file <filepath>")
                else:
                    instruction = " ".join(parts[2:]) if len(parts) > 2 else "Review this file:"
                    fp = load_file_as_prompt(parts[1], instruction)
                    if fp is None:
                        print_error(f"File not found: {parts[1]}")
                    elif fp.startswith("ERROR:"):
                        print_error(fp)
                    else:
                        print_info("Sending file to model...")
                        ask_model(fp, free_models)

            # ---- Project ----
            elif cmd == "/project":
                if len(parts) < 2:
                    print_error("Usage: /project <folder>")
                else:
                    instruction = " ".join(parts[2:]) if len(parts) > 2 else "Review this project:"
                    pp = load_project_as_prompt(parts[1], instruction)
                    if pp is None:
                        print_error(f"Folder not found: {parts[1]}")
                    elif pp.startswith("ERROR:"):
                        print_error(pp)
                    else:
                        print_info("Sending project to model...")
                        ask_model(pp, free_models)

            # ---- Savecode ----
            elif cmd == "/savecode":
                last_resp = next(
                    (m["content"] for m in reversed(state.conversation) if m["role"] == "assistant"),
                    None,
                )
                if last_resp:
                    save_code_interactive(last_resp)
                else:
                    print_error("No assistant response in history.")

            # ---- Select ----
            elif cmd == "/select":
                with _thinking_spinner(["Refreshing available models..."]):
                    free_models = get_free_models()
                if free_models:
                    new_model = choose_model(free_models)
                    if new_model:
                        state.current_model = new_model
                        set_last_model(new_model)
                        print_success(f"Selected: {state.current_model['name']}")
                        if state.conversation:
                            try:
                                clear_choice = input(
                                    f"Start fresh conversation with {state.current_model['name']}? (y/n) [default: y]: "
                                ).strip().lower()
                            except (EOFError, KeyboardInterrupt):
                                clear_choice = "y"
                            if clear_choice in ("", "y", "yes"):
                                state.conversation = []
                                print_info("Started fresh conversation.")
                            else:
                                print_info(f"Retained {len(state.conversation)} messages in history.")
                else:
                    print_error("No free models available.")

            # ---- Models ----
            elif cmd == "/models":
                with _thinking_spinner(["Fetching free models list..."]):
                    free_models = get_free_models()
                display_model_table(free_models)

            # ---- Save / Load / Export ----
            elif cmd == "/save":
                save_conversation()

            elif cmd == "/load":
                load_conversation()

            elif cmd == "/export":
                export_as_markdown()

            # ---- Tokens ----
            elif cmd == "/tokens":
                total_chars = sum(
                    len(m.get("content", "")) if isinstance(m.get("content"), str)
                    else sum(len(p.get("text", "")) for p in m.get("content", []) if p.get("type") == "text")
                    for m in state.conversation
                )
                est = total_chars // CHARS_PER_TOKEN
                ctx = state.current_model.get("context", 0) if state.current_model else 0
                if HAS_RICH:
                    t = Table(title="Token Usage", box=box.ROUNDED)
                    t.add_column("Metric", style="bold")
                    t.add_column("Value", style="cyan", justify="right")
                    t.add_row("Messages", str(len(state.conversation)))
                    t.add_row("Characters", f"{total_chars:,}")
                    t.add_row("Est. Tokens", f"{est:,}")
                    if isinstance(ctx, int) and ctx > 0:
                        pct = (est / ctx) * 100
                        col = "green" if pct < 50 else "yellow" if pct < 80 else "red"
                        t.add_row("Context Limit", format_ctx(ctx))
                        t.add_row("Usage", f"[{col}]{pct:.1f}%[/]")
                    console.print(t)
                else:
                    print(f"Messages: {len(state.conversation)}\nEst. Tokens: {est:,}")

            # ---- History limit ----
            elif cmd == "/history":
                if len(parts) < 2:
                    cur = state.history_limit
                    cur_disp = "unlimited" if cur is None else cur
                    print_info(f"History limit: {cur_disp} (current turns: {len(state.conversation)})")
                else:
                    try:
                        n = int(parts[1])
                        if n <= 0:
                            state.history_limit = None
                            print_success("History limit removed (keeping all turns).")
                        else:
                            state.history_limit = n
                            if len(state.conversation) > state.history_limit:
                                state.conversation = state.conversation[-state.history_limit:]
                            print_success(f"History limited to last {n} message(s).")
                    except ValueError:
                        print_error("Usage: /history <N>  (N = number of messages to keep, 0 = unlimited)")

            # ---- Workspace ----
            elif cmd == "/workspace":
                if len(parts) < 2:
                    cur = state.workspace_root or os.getcwd()
                    print_info(f"Current workspace: {cur}")
                else:
                    new_ws = os.path.abspath(parts[1])
                    if not os.path.isdir(new_ws):
                        print_error(f"Not a directory: {new_ws}")
                    else:
                        state.workspace_root = new_ws
                        print_success(f"Workspace set to {new_ws}")

            # ---- Allow bash ----
            elif cmd == "/allow":
                if len(parts) < 2:
                    status = "ON" if state.allow_bash else "OFF"
                    print_info(f"Bash tool: {status}")
                else:
                    val = parts[1].lower()
                    if val in ("on", "true", "yes", "1", "bash"):
                        state.allow_bash = True
                        print_success("Bash tool ENABLED — model can run shell commands in workspace.")
                    elif val in ("off", "false", "no", "0"):
                        state.allow_bash = False
                        print_success("Bash tool DISABLED.")
                    else:
                        print_error("Usage: /allow <on|off>")

            # ---- Clear ----
            elif cmd == "/clear":
                state.conversation = []
                print_warn("Conversation cleared.")

            # ---- Exit ----
            elif cmd == "/exit":
                print_warn("Saving and exiting...")
                save_conversation()
                break

            else:
                # Smart command suggestions using shared registry
                matches = [(c, d) for c, d, _ in COMMAND_REGISTRY if c.startswith(cmd)]
                if not matches:
                    matches = [(c, d) for c, d, _ in COMMAND_REGISTRY if cmd[1:] in c]

                if matches:
                    print_warn(f"Unknown command: {cmd}. Did you mean:")
                    for name, desc in matches:
                        print_info(f"  {name:14s} {desc}")
                else:
                    print_error(f"Unknown command: {cmd}. Type /help for all commands.")

        except KeyboardInterrupt:
            print_warn("\nInterrupted. Type /exit to quit.")
        except EOFError:
            print_warn("\nSaving and exiting...")
            save_conversation()
            break


if __name__ == "__main__":
    main()
