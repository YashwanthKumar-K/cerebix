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

def run_consensus(prompt, free_models):
    """Ask multiple models the same question, then synthesize a best answer."""
    display_model_table(free_models, title="Select Jury Models")

    while True:
        raw = input("\nJury model numbers (comma-separated, e.g. '2,7,11'): ").strip()
        if not raw:
            print_warn("Cancelled.")
            return
        try:
            indices = [int(x.strip()) for x in raw.split(",")]
            selected = [free_models[i] for i in indices if 0 <= i < len(free_models)]
            if len(selected) < 2:
                print_error("Need at least 2 models.")
                continue
            break
        except (ValueError, IndexError):
            print_error("Invalid input. Use comma-separated numbers.")

    print_info(f"\nQuerying {len(selected)} models in parallel...")
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
            print_success(f"Got response from {name}")
        results.append((name, mid, text))

    # Display individual responses
    print_info("\n=== Individual Responses ===")
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

    # Synthesize
    if input("\nSynthesize into one best answer? (y/n): ").strip().lower() != "y":
        return

    synthesis_prompt = (
        f"You are synthesizing multiple AI responses to the same question as an expert judge.\n\n"
        f"Original question:\n{prompt}\n\n"
        f"Instructions:\n"
        f"1. Weight factual claims carefully based on the reasoning and evidence provided in each response.\n"
        f"2. Explicitly note any points where models disagree or contradict each other, and clarify which perspective is most accurate.\n"
        f"3. If you are genuinely uncertain which response is correct on a specific detail, state that uncertainty rather than guessing.\n"
        f"4. Eliminate redundancies and produce a comprehensive, structured response formatted in clean markdown:\n"
        f"   - **Summary & Consensus** (core points all models agree on)\n"
        f"   - **Key Nuances & Disagreements** (different perspectives or edge cases noted)\n"
        f"   - **Comprehensive Answer** (unified, complete solution)\n\n"
    )
    for i, (name, mid, text) in enumerate(results, 1):
        synthesis_prompt += f"--- Response {i} (Model: {name} | ID: {mid}) ---\n{text}\n\n"

    judge = state.current_model or free_models[0]
    print_info(f"Synthesizing with {judge['name']}...")
    with _thinking_spinner(_SYNTHESIS_MESSAGES):
        synthesized = ask_model_isolated(synthesis_prompt, judge["id"])

    if HAS_RICH:
        console.print()
        console.print(Panel(
            Markdown(synthesized),
            title="[bold cyan]Synthesized Answer[/]",
            border_style="cyan",
            box=box.DOUBLE,
        ))
    else:
        print(f"\n=== Synthesized Answer ===\n{synthesized}")

    # Add to state.conversation
    state.conversation.append({"role": "user", "content": prompt})
    state.conversation.append({"role": "assistant", "content": synthesized})


