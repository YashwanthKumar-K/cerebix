from concurrent.futures import ThreadPoolExecutor, as_completed
from . import state
from .config import print_error, print_warn, print_success, print_info, HAS_RICH, console
from .models import display_model_table
from .api import ask_model_isolated
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

    with ThreadPoolExecutor(max_workers=len(selected)) as ex:
        futures = {ex.submit(ask_model_isolated, prompt, m["id"]): m for m in selected}
        for future in as_completed(futures):
            m = futures[future]
            try:
                text = future.result()
                results.append((m["name"], m["id"], text))
                print_success(f"Received from {m['name']}")
            except Exception as e:
                results.append((m["name"], m["id"], f"Error: {e}"))
                print_error(f"Error from {m['name']}: {e}")

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
            f"Synthesize the following responses to: '{prompt}'\n\n"
        )
        for i, (name, _, text) in enumerate(results, 1):
            synth_prompt += f"--- Response {i} ({name}) ---\n{text}\n\n"
        judge = state.current_model or free_models[0]
        print_info(f"Synthesizing with {judge['name']}...")
        synth = ask_model_isolated(synth_prompt, judge["id"])
        if HAS_RICH:
            console.print()
            console.print(Panel(Markdown(synth), title="[bold cyan]Synthesis[/]", border_style="cyan", box=box.DOUBLE))
        else:
            print(f"\n=== Synthesis ===\n{synth}")


