import re
from . import state
from .config import print_info, print_warn
from .scorecard import scorecard_best

_ROUTE_PATTERNS = {
    "code": re.compile(
        r"\b(code|script|function|class|debug|bug|error|implement|refactor|algorithm|"
        r"python|javascript|typescript|java|c\+\+|golang|rust|sql|html|css|api|regex|"
        r"program|compile|syntax|library|framework|module|import|variable|loop|array)\b",
        re.IGNORECASE,
    ),
    "math": re.compile(
        r"\b(equation|solve|calculate|math|algebra|calculus|statistics|probability|"
        r"integral|derivative|matrix|vector|proof|theorem|formula|compute|numerically|"
        r"graph|plot|function|polynomial|coefficient|sum|product|factorial)\b",
        re.IGNORECASE,
    ),
    "creative": re.compile(
        r"\b(write|story|poem|creative|fiction|character|narrative|brainstorm|idea|"
        r"slogan|marketing|blog|essay|name|title|metaphor|song|script|dialogue|"
        r"imagine|invent|describe|fantasy|humor|joke|rhyme)\b",
        re.IGNORECASE,
    ),
    "reasoning": re.compile(
        r"\b(analyze|compare|explain|why|how|reason|argument|evaluate|pros|cons|"
        r"debate|opinion|think|recommend|decision|strategy|critique|assess|impact|"
        r"cause|effect|difference|versus|vs|tradeoff|advice|suggest)\b",
        re.IGNORECASE,
    ),
    "documentation": re.compile(
        r"\b(readme|document|docs|docstring|comment|tutorial|guide|manual|explain|"
        r"summarize|wiki|api doc|specification|changelog|report|notes|instructions)\b",
        re.IGNORECASE,
    ),
}


def classify_prompt(prompt):
    """Classify a prompt into one of the scorecard categories."""
    scores = {cat: len(pat.findall(prompt)) for cat, pat in _ROUTE_PATTERNS.items()}
    best_cat = max(scores, key=scores.get)
    return best_cat if scores[best_cat] > 0 else "general"


# Name-based heuristics: ordered by preference — first keyword that matches wins.
# IMPORTANT: keep weak/generic terms like "instruct" OUT of reasoning/math —
# they match nano/tiny models that appear first in the list.
_HEURISTIC_KEYWORDS = {
    "code":          ["deepseek-coder", "starcoder", "mini-code", "qwen-coder",
                      "coder", "coding", "code"],
    "math":          ["deepseek-r1", "r1", "qwq", "thinking", "reasoning", "math",
                      "ultra"],
    "reasoning":     ["deepseek-r1", "r1", "qwq", "thinking", "reasoning",
                      "ultra", "nemotron-ultra", "nemotron-3-ultra"],
    "creative":      ["lyria", "creative", "claude", "gemma", "llama", "story"],
    "documentation": ["glm", "gemma", "mini", "light", "small", "nano"],
    "general":       [],
}

# Models that should NEVER be picked for planning/reasoning tasks
# (too small/weak despite matching keywords)
_WEAK_MODEL_HINTS = ["nano", "tiny", "mini", "1b", "3b", "7b", "omni"]


def _is_weak(model):
    """Return True if this model is likely a small/weak model."""
    combined = (model["id"] + " " + model["name"]).lower()
    return any(hint in combined for hint in _WEAK_MODEL_HINTS)


def _pick_by_context(free_models, exclude_weak=False):
    """Fallback: pick the model with the largest context window (proxy for capability)."""
    candidates = [m for m in free_models if not (exclude_weak and _is_weak(m))]
    if not candidates:
        candidates = free_models  # if all are "weak", use everything
    return max(candidates, key=lambda m: m.get("context", 0) or 0)


def _heuristic_pick(category, free_models, exclude_weak=False):
    """Pick a model by keyword matching. Skips weak models if exclude_weak=True.
    Falls back to largest-context model if no keyword match found."""
    candidates = [m for m in free_models if not (exclude_weak and _is_weak(m))]
    if not candidates:
        candidates = free_models

    for kw in _HEURISTIC_KEYWORDS.get(category, []):
        for m in candidates:
            if kw in m["id"].lower() or kw in m["name"].lower():
                return m

    # No keyword match — fall back to largest context window
    if category in ("reasoning", "math"):
        return _pick_by_context(free_models, exclude_weak=True)

    return None


def route_model(prompt, free_models):
    """Pick the best model for this prompt when state.auto_routing is on.

    Priority:
      1. Scorecard best (data learned from past sessions)
      2. Name-based heuristic (built-in keyword matching on model names)
      3. Fall back to state.current_model
    """
    if not state.auto_routing:
        return state.current_model

    category = classify_prompt(prompt)

    # 1 — Scorecard (learned data takes highest priority)
    best_id = scorecard_best(category)
    if best_id:
        for m in free_models:
            if m["id"] == best_id:
                print_info(f"[Auto-route][scorecard] '{category}' -> {m['name']}")
                return m

    # 2 — Name-based heuristic (works even with empty scorecard)
    pick = _heuristic_pick(category, free_models)
    if pick and pick["id"] != (state.current_model or {}).get("id"):
        print_info(f"[Auto-route][heuristic] '{category}' -> {pick['name']}")
        return pick

    # 3 — Fallback
    print_info(f"[Auto-route] '{category}' — no better match, using {(state.current_model or {}).get('name', '?')}")
    return state.current_model


