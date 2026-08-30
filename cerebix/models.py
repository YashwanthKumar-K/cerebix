import requests
import sys
from .config import print_error, print_info, HEADERS, HAS_RICH, console
if HAS_RICH:
    from rich.table import Table
    from rich import box

# Providers/model prefixes restricted to agentic harnesses (always 403 via raw API).
# Add any provider slug here to permanently exclude it from Cerebix.
_BLOCKED_PROVIDERS = [
    "thinkingmachines",  # 403: only available on agentic harnesses
    "lyria",             # Mistakenly reported as free by OpenRouter, causing charges
]


def _is_blocked(model_id):
    """Return True if this model is from a restricted/broken provider."""
    mid = model_id.lower()
    return any(mid.startswith(p) or ("/" + p) in mid for p in _BLOCKED_PROVIDERS)


def get_free_models():
    """Fetch all free models from OpenRouter, excluding blocked providers."""
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        print_error(f"Failed to fetch models: {e}")
        return []

    free = []
    for m in r.json().get("data", []):
        pricing = m.get("pricing", {})
        try:
            pp = float(pricing.get("prompt", "1"))
            cp = float(pricing.get("completion", "1"))
        except (ValueError, TypeError):
            continue
        model_id = m.get("id", "")

        # Skip permanently blocked/restricted providers
        if _is_blocked(model_id):
            continue

        # BULLETPROOF FIX: We no longer trust OpenRouter's metadata pricing (pp == 0 and cp == 0)
        # because of API glitches. A model MUST explicitly have the ":free" tag to be used.
        is_free = model_id.endswith(":free")
        
        if is_free:
            ctx = m.get("context_length", 0)
            try:
                ctx = int(ctx) if ctx else 0
            except (ValueError, TypeError):
                ctx = 0
            free.append({"id": model_id, "name": m.get("name", model_id), "context": ctx})
    return free



def format_ctx(ctx):
    """Format context length nicely: 262144 -> '262k'."""
    if not ctx or ctx == 0:
        return "N/A"
    try:
        v = int(ctx)
    except (ValueError, TypeError):
        return str(ctx)
    if v >= 1_000_000:
        return f"{round(v / 1_000_000)}M"
    if v >= 1_000:
        return f"{round(v / 1_000)}k"
    return str(v)


def display_model_table(models, title="Free Models"):
    """Print a Rich table of models."""
    if HAS_RICH:
        table = Table(title=f"{title} ({len(models)} available)", box=box.ROUNDED, show_lines=False)
        table.add_column("#",            style="bold cyan",  justify="right", width=4)
        table.add_column("Model Name",   style="bold white")
        table.add_column("Context",      style="green",      justify="right")
        table.add_column("ID",           style="dim")
        for i, m in enumerate(models):
            table.add_row(str(i), m["name"], format_ctx(m["context"]), m["id"])
        console.print()
        console.print(table)
    else:
        print(f"\n{title} ({len(models)} available):\n")
        for i, m in enumerate(models):
            print(f"  [{i}] {m['name']}  (ctx: {format_ctx(m['context'])})  -> {m['id']}")


def choose_model(free_models):
    """Interactive model picker. Returns the chosen model dict."""
    display_model_table(free_models)
    while True:
        try:
            choice = input("\nPick a model number: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if choice.isdigit() and 0 <= int(choice) < len(free_models):
            return free_models[int(choice)]
        
        # Allow typing an exact ID
        for m in free_models:
            if m["id"] == choice:
                return m

        print_error(f"Enter a number between 0 and {len(free_models) - 1}, or a valid model ID.")


