import json
from . import state
from .config import SCORECARD_FILE, print_warn, print_info, print_error, HAS_RICH, console
if HAS_RICH:
    from rich.table import Table
    from rich import box

CATEGORIES = ["code", "math", "creative", "reasoning", "documentation", "general"]

state._scorecard = {}   # {model_id: {category: [scores]}}


def scorecard_load():

    try:
        with open(SCORECARD_FILE, "r", encoding="utf-8") as f:
            state._scorecard = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state._scorecard = {}


def scorecard_save():
    with open(SCORECARD_FILE, "w", encoding="utf-8") as f:
        json.dump(state._scorecard, f, indent=2)


def scorecard_record(model_id, category, score):
    state._scorecard.setdefault(model_id, {}).setdefault(category, []).append(score)
    scorecard_save()


def scorecard_best(category):
    """Return model_id with highest average score for a category."""
    best_id, best_avg = None, -1
    for mid, cats in state._scorecard.items():
        scores = cats.get(category, [])
        if scores:
            avg = sum(scores) / len(scores)
            if avg > best_avg:
                best_avg = avg
                best_id = mid
    return best_id


def scorecard_display():
    if not state._scorecard:
        print_warn("No scorecard data yet. Chat using /auto mode to build it up.")
        return
    if HAS_RICH:
        table = Table(title="Model Scorecard", box=box.ROUNDED)
        table.add_column("Model ID", style="bold white")
        for cat in CATEGORIES:
            table.add_column(cat.capitalize(), style="cyan", justify="right")
        for mid, cats in state._scorecard.items():
            row = [mid]
            for cat in CATEGORIES:
                scores = cats.get(cat, [])
                row.append(f"{sum(scores)/len(scores):.0f}" if scores else "-")
            table.add_row(*row)
        console.print(table)
    else:
        print("\n--- Scorecard ---")
        for mid, cats in state._scorecard.items():
            print(f"\n{mid}:")
            for cat in CATEGORIES:
                scores = cats.get(cat, [])
                avg = f"{sum(scores)/len(scores):.0f}" if scores else "-"
                print(f"  {cat}: {avg}")


