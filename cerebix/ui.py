import sys
from . import state
from .config import HAS_RICH, console, Fore, Style, print_success, print_info, print_error
from .models import choose_model
if HAS_RICH:
    from rich.text import Text
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich import box

def show_banner():
    banner = r"""
   ____ _____ ____  _____ ____  ______  __
  / ___| ____|  _ \| ____| __ )|_ _\ \/ /
 | |   |  _| | |_) |  _| |  _ \ | | \  / 
 | |___| |___|  _ <| |___| |_) || | /  \ 
  \____|_____|_| \_\_____|____/|___/_/\_\
"""
    if HAS_RICH:
        console.print(Text(banner, style="bold cyan"))
        console.print(Panel.fit(
            "[bold white]Cerebix — Multi-Model AI Orchestration CLI[/]\n"
            "[dim]Powered by OpenRouter • 20+ Free Models • /help for commands[/]",
            border_style="cyan",
            box=box.DOUBLE,
        ))
    else:
        print(f"{Fore.CYAN}{banner}{Style.RESET_ALL}")
        print("  Cerebix — Multi-Model AI Orchestration CLI")
        print("  Powered by OpenRouter • 20+ Free Models • /help for commands\n")


def show_help():
    text = """
## 💬 Chat
| Command | Description |
|---|---|
| *(type anything)* | Chat with the current model |
| `/render` | Toggle response display mode (`panel` vs `stream`) |
| `/ssl` | Toggle SSL verification for captive portals/proxies |
| `/system <text>` | Set a system persona/instruction |
| `/system` | View or clear current system prompt |

## 🧭 Model Selection
| Command | Description |
|---|---|
| `/select` | Pick a different model |
| `/models` | List all available free models |
| `/auto` | Toggle smart auto-routing (picks best model per task) |
| `/scores` | View the model performance scorecard |

## 🤖 Multi-Model Modes
| Command | Description |
|---|---|
| `/debate <topic>` | **AI Arena** — two models debate (PRO vs CON) across rounds + judge verdict |
| `/collab <topic>` | **Critic-Refiner** — one model plans, another critiques, loop until approved |
| `/consensus <prompt>` | Jury mode — query 2+ models, then synthesize |
| `/fanout <prompt>` | Send same prompt to multiple models in parallel |
| `/build <description>` | **Project Build** — plan + generate a full multi-file project to disk |

## 🏗️ Project Build Mode (/build)
Describe what you want and Cerebix builds it in 3 phases:

**Phase 1 — Plan:** A reasoning model outputs a full JSON file structure
(every file, its purpose, and cross-file dependencies).
You review and confirm the plan before anything is written.

**Phase 2 — Generate:** Each file is generated separately with the full
project manifest as context, so imports stay consistent across files.

**Phase 3 — Write:** All files are saved to a local folder of your choice.
A CEREBIX_BUILD.md manifest is created listing every file's status.

Examples:
  /build A Flask REST API with JWT auth and SQLite
  /build A Python CLI to-do app saved to a JSON file
  /build A static portfolio website with HTML, CSS, and JS

Tip: Use /select to pick a strong model (Nemotron Ultra, DeepSeek R1)
before /build for best results. Weaker models may fail the planning phase.

## 📁 Context
| Command | Description |
|---|---|
| `/file <path>` | Send a file for review |
| `/project <path>` | Send an entire project folder |
| `/savecode` | Extract & save code blocks from last response |

## 💾 Session
| Command | Description |
|---|---|
| `/save` | Save state.conversation |
| `/load` | Load previous state.conversation |
| `/export` | Export state.conversation as markdown |
| `/tokens` | Show token usage estimate |
| `/clear` | Clear state.conversation history |
| `/exit` | Save & exit |
"""
    if HAS_RICH:
        console.print(Panel(Markdown(text), title="[bold cyan]Cerebix Commands[/]", border_style="cyan", box=box.ROUNDED))
    else:
        print(text)


def select_startup_mode(free_models, saved_model=None, history_count=0):
    """Prompt user to pick a startup mode (Auto, Manual, Quick Start, or Resume Session)."""

    fallback_name = saved_model["name"] if saved_model else free_models[0]["name"]
    has_history = history_count > 0

    if HAS_RICH:
        options = (
            "[bold cyan][1][/] [bold white]Smart Auto Mode[/] [bold green](Recommended)[/]\n"
            "    [dim]Fresh session: dynamically picks best model per prompt (coding, reasoning, etc.)[/]\n\n"
            "[bold cyan][2][/] [bold white]Manual Mode[/]\n"
            "    [dim]Fresh session: browse the list of available free models and pick one yourself[/]\n\n"
            "[bold cyan][3][/] [bold white]Quick Start[/]\n"
            f"    [dim]Fresh session: instantly start chatting using {fallback_name}[/]"
        )
        if has_history:
            options += (
                f"\n\n[bold cyan][4][/] [bold white]Resume Previous Session[/]\n"
                f"    [dim]Continue your saved conversation ({history_count} messages with {fallback_name})[/]"
            )
        console.print()
        console.print(Panel(options, title="[bold cyan]Select Startup Mode[/]", border_style="cyan", box=box.ROUNDED))
    else:
        print("\n=== Select Startup Mode ===")
        print("  [1] Smart Auto Mode (Recommended) - Fresh session, auto-routes to best model")
        print("  [2] Manual Mode - Fresh session, choose a specific model from the list")
        print(f"  [3] Quick Start - Fresh session, use {fallback_name} immediately")
        if has_history:
            print(f"  [4] Resume Previous Session - Continue previous {history_count} messages")

    valid_range = "[1-4]" if has_history else "[1-3]"
    while True:
        try:
            choice = input(f"\nPick a mode {valid_range} (default: 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)

        if not choice or choice == "1":
            state.conversation = []
            state.auto_routing = True
            state.current_model = saved_model if saved_model else free_models[0]
            print_success(f"Started in Smart Auto Mode! (Fallback: {state.current_model['name']})")
            print_info("Fresh session ready. Cerebix will automatically route your questions to the best model.")
            break
        elif choice == "2":
            state.conversation = []
            state.auto_routing = False
            state.current_model = choose_model(free_models)
            print_success(f"Selected: {state.current_model['name']} ({state.current_model['id']})")
            print_info("Fresh session ready.")
            break
        elif choice == "3":
            state.conversation = []
            state.auto_routing = False
            state.current_model = saved_model if saved_model else free_models[0]
            print_success(f"Started with: {state.current_model['name']}")
            print_info("Fresh session ready.")
            break
        elif choice == "4" and has_history:
            from .persistence import load_conversation
            load_conversation()
            state.auto_routing = False
            state.current_model = saved_model if saved_model else free_models[0]
            print_success(f"Resumed previous session with {state.current_model['name']} ({len(state.conversation)} messages).")
            break
        else:
            print_error(f"Please enter a number between 1 and {4 if has_history else 3}.")


