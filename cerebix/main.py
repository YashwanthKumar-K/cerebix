import shlex
import sys
if True:
    try:
        from rich.table import Table
        from rich import box
    except ImportError:
        pass
from . import state
from .config import check_api_key, print_info, print_error, print_warn, print_success, HAS_RICH, console, Fore, Style, CHARS_PER_TOKEN
from .ui import show_banner, show_help, select_startup_mode
from .scorecard import scorecard_load, scorecard_display, scorecard_record
from .persistence import load_conversation, save_conversation, export_as_markdown
from .models import get_free_models, display_model_table, choose_model, format_ctx
from .main_chat import ask_model
from .routing import classify_prompt
from .consensus import run_consensus
from .fanout import fan_out
from .build import run_project_build
from .context import load_file_as_prompt, load_project_as_prompt
from .utils import save_code_interactive

def main():

    
    check_api_key()

    show_banner()
    scorecard_load()
    saved_model = load_conversation()

    # Fetch models
    print_info("Fetching free models from OpenRouter...")
    free_models = get_free_models()
    if not free_models:
        print_error("No free models found. Check your API key.")
        return

    # Startup mode selection
    select_startup_mode(free_models, saved_model)

    # Main loop
    while True:
        try:
            if HAS_RICH:
                user_input = console.input("\n[bold green]You:[/] ")
            else:
                user_input = input(f"\n{Fore.GREEN}You:{Style.RESET_ALL} ")

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
                free_models = get_free_models()
                if free_models:
                    state.current_model = choose_model(free_models)
                    print_success(f"Selected: {state.current_model['name']}")
                else:
                    print_error("No free models available.")

            # ---- Models ----
            elif cmd == "/models":
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
                print_error(f"Unknown command: {cmd}. Type /help.")

        except KeyboardInterrupt:
            print_warn("\nInterrupted. Type /exit to quit.")
        except EOFError:
            print_warn("\nSaving and exiting...")
            save_conversation()
            break


if __name__ == "__main__":
    main()
