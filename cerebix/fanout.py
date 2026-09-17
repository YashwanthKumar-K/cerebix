from concurrent.futures import ThreadPoolExecutor, as_completed
from . import state
from .config import print_error, print_warn, print_success, print_info, HAS_RICH, console
from .models import display_model_table
from .api import ask_model_isolated
from .spinner import _thinking_spinner, _PARALLEL_MESSAGES, _SYNTHESIS_MESSAGES
if HAS_RICH:
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich import box

def fan_out(prompt, free_models):
    """Send same prompt to multiple chosen models in parallel."""
    display_model_table(free_models, title="Select Fan-out Models")

    while True:
        raw = input("\nModel numbers (comma-separated): ").strip()
        if not raw:
            print_warn("Cancelled.")
            return
        try:
            indices = [int(x.strip()) for x in raw.split(",")]
            selected = [free_models[i] for i in indices if 0 <= i < len(free_models)]
            if not selected:
                print_error("No valid models selected.")
                continue
            break
        except (ValueError, IndexError):
            print_error("Invalid input.")

    print_info(f"\nSending to {len(selected)} model(s)...")
    results = []

    with _thinking_spinner(_PARALLEL_MESSAGES):
        with ThreadPoolExecutor(max_workers=len(selected)) as ex:
            futures = {ex.submit(ask_model_isolated, prompt, m["id"]): m for m in selected}
            raw_results = []
            for future in as_completed(futures):
                m = futures[future]
                try:
                    text = future.result()
                    raw_results.append((m["name"], m["id"], text, None))
                except Exception as e:
                    raw_results.append((m["name"], m["id"], f"Error: {e}", e))

    for name, mid, text, err in raw_results:
        if err:
            print_error(f"Error from {name}: {err}")
        else:
            print_success(f"Received from {name}")
        results.append((name, mid, text))

    for name, mid, text in results:
        if HAS_RICH:
            console.print()
            console.print(Panel(
                Markdown(text),
                title=f"[bold yellow]{name}[/]",
                subtitle=f"[dim]{mid}[/]",
                border_style="yellow",
                box=box.ROUNDED,
            ))
        else:
            print(f"\n--- {name} ({mid}) ---\n{text}")

    # Optional synthesis
    if input("\nSynthesize? (y/n): ").strip().lower() == "y":
        synth_prompt = (
            f"You are an expert research synthesizer. You have queried multiple AI models with the prompt: '{prompt}'\n\n"
            f"Your goals:\n"
            f"1. Identify the unique contributions, ideas, or insights each model provided.\n"
            f"2. Highlight where the models agree and where their approaches diverge.\n"
            f"3. Produce a cohesive, unified synthesis that combines the best points into a single definitive answer.\n\n"
            f"Format your output in clean markdown:\n"
            f"- **Consensus Overview**\n"
            f"- **Comparative Analysis & Distinct Insights**\n"
            f"- **Unified Synthesis**\n\n"
        )
        for i, (name, mid, text) in enumerate(results, 1):
            synth_prompt += f"--- Response {i} (Model: {name} | ID: {mid}) ---\n{text}\n\n"
        judge = state.current_model or free_models[0]
        print_info(f"Synthesizing with {judge['name']}...")
        with _thinking_spinner(_SYNTHESIS_MESSAGES):
            synth = ask_model_isolated(synth_prompt, judge["id"])
        if HAS_RICH:
            console.print()
            console.print(Panel(Markdown(synth), title="[bold cyan]Synthesis[/]", border_style="cyan", box=box.DOUBLE))
        else:
            print(f"\n=== Synthesis ===\n{synth}")


