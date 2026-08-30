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


def select_startup_mode(free_models, saved_model=None):
    """Prompt user to pick a startup mode (Auto, Manual model picker, or Quick Start)."""


    fallback_name = saved_model["name"] if saved_model else free_models[0]["name"]

    if HAS_RICH:
        options = (
            "[bold cyan][1][/] [bold white]Smart Auto Mode[/] [bold green](Recommended)[/]\n"
            "    [dim]Cerebix dynamically picks the best specialized model for each prompt (coding, reasoning, etc.)[/]\n\n"
            "[bold cyan][2][/] [bold white]Manual Mode[/]\n"
            "    [dim]Browse the list of available free models and pick one yourself[/]\n\n"
            "[bold cyan][3][/] [bold white]Quick Start[/]\n"
            f"    [dim]Instantly start chatting using {fallback_name}[/]"
        )
        console.print()
        console.print(Panel(options, title="[bold cyan]Select Startup Mode[/]", border_style="cyan", box=box.ROUNDED))
    else:
        print("\n=== Select Startup Mode ===")
        print("  [1] Smart Auto Mode (Recommended) - Auto-routes each prompt to the best model")
        print("  [2] Manual Mode - Choose a specific model from the list")
        print(f"  [3] Quick Start - Use {fallback_name} immediately")

    while True:
        try:
            choice = input("\nPick a mode [1-3] (default: 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)

        if not choice or choice == "1":
            state.auto_routing = True
            state.current_model = saved_model if saved_model else free_models[0]
            print_success(f"Started in Smart Auto Mode! (Fallback: {state.current_model['name']})")
            print_info("Cerebix will automatically route your questions to the best model.")
            break
        elif choice == "2":
            state.auto_routing = False
            state.current_model = choose_model(free_models)
            print_success(f"Selected: {state.current_model['name']} ({state.current_model['id']})")
            break
        elif choice == "3":
            state.auto_routing = False
            state.current_model = saved_model if saved_model else free_models[0]
            print_success(f"Started with: {state.current_model['name']}")
            break
        else:
            print_error("Please enter 1, 2, or 3.")


