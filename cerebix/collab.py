"""
cerebix/collab.py

/collab — Critic-Refiner Collaborative Loop
One model plans, another critiques via structured JSON, planner revises.
Loop continues until critic approves (confidence >= threshold) or max rounds hit.

Usage:
    /collab Design a REST API for a task manager
    /collab Optimize a Python scraper --rounds 3 --threshold 80
    /collab Plan a CLI todo app --rounds 4 --swap
"""

from __future__ import annotations

import json
import re
from typing import Optional

from . import state
from .config import HAS_RICH, console, print_error, print_warn
from .api import ask_model_isolated
from .spinner import ThinkingSpinner
from .models import display_model_table

if HAS_RICH:
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    from rich.text import Text


# ── System Prompts (~60 tokens each) ────────────────────────────────────────

PLANNER_SYSTEM = (
    "You are a senior architect. Produce clear, structured plans. "
    "When given critique: address every point, state what changed and why, "
    "output the FULL revised plan — never a partial diff."
)

CRITIC_SYSTEM = (
    "You are a rigorous reviewer. Respond ONLY in this exact JSON — no prose, no fences:\n"
    '{"confidence": <0-100>, "approved": <true|false>, '
    '"issues": [{"severity": "critical|major|minor", "location": "<section>", '
    '"problem": "<what is wrong>", "suggestion": "<concrete fix>"}], '
    '"praise": "<one sentence on what works>", "summary": "<two sentence assessment>"}\n'
    "Never approve a plan that has unresolved critical issues."
)


# ── Argument Parsing ─────────────────────────────────────────────────────────

def _parse_collab_args(raw: str) -> tuple[str, int, int, bool]:
    """
    Parse: /collab <topic> [--rounds N] [--threshold N] [--swap]
    Returns: (topic, rounds, threshold, swap)
    """
    rounds_match = re.search(r"--rounds\s+(\d+)", raw)
    threshold_match = re.search(r"--threshold\s+(\d+)", raw)
    swap = "--swap" in raw

    rounds = int(rounds_match.group(1)) if rounds_match else 5
    threshold = int(threshold_match.group(1)) if threshold_match else 85

    # Strip flags from topic
    topic = re.sub(r"--rounds\s+\d+", "", raw)
    topic = re.sub(r"--threshold\s+\d+", "", topic)
    topic = topic.replace("--swap", "").strip()

    # Clamp rounds and threshold to sensible ranges
    rounds = max(1, min(rounds, 10))
    threshold = max(50, min(threshold, 100))

    return topic, rounds, threshold, swap


# ── Model Selection ──────────────────────────────────────────────────────────

def _pick_collab_models(
    free_models: list[dict],
) -> tuple[Optional[dict], Optional[dict]]:
    """
    Interactive model picker following debate.py pattern.
    Displays a numbered table; user picks Planner and Critic by index.
    Falls back to auto-select if input is blank.
    Returns (planner_model_dict, critic_model_dict) or (None, None) on abort.
    """
    if len(free_models) < 2:
        print_error("Need at least 2 available models for /collab.")
        return None, None

    current_model_id = state.current_model["id"] if state.current_model else ""

    # Display model table (reuse existing helper)
    display_model_table(free_models, title="Select Collaborators")

    # Auto-select defaults
    current_idx = next(
        (i for i, m in enumerate(free_models) if m["id"] == current_model_id), 0
    )
    best_context_idx = max(
        range(len(free_models)),
        key=lambda i: free_models[i].get("context", 0)
    )
    alt_idx = best_context_idx if best_context_idx != current_idx else (
        (current_idx + 1) % len(free_models)
    )

    if HAS_RICH:
        console.print(
            f"\n[dim]Auto-select: Planner=[{current_idx}] {free_models[current_idx]['id']}, "
            f"Critic=[{alt_idx}] {free_models[alt_idx]['id']}[/dim]"
        )
    else:
        print(f"\nAuto-select: Planner=[{current_idx}], Critic=[{alt_idx}]")

    try:
        planner_input = input(f"Pick Planner index (Enter = {current_idx}): ").strip()
        critic_input = input(f"Pick Critic index  (Enter = {alt_idx}): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return None, None

    planner_idx = int(planner_input) if planner_input.isdigit() else current_idx
    critic_idx = int(critic_input) if critic_input.isdigit() else alt_idx

    # Validate range
    if not (0 <= planner_idx < len(free_models)):
        print_error(f"Invalid planner index {planner_idx}.")
        return None, None
    if not (0 <= critic_idx < len(free_models)):
        print_error(f"Invalid critic index {critic_idx}.")
        return None, None
    if planner_idx == critic_idx:
        print_error("Planner and Critic must be different models.")
        return None, None

    return free_models[planner_idx], free_models[critic_idx]


# ── JSON Parsing ─────────────────────────────────────────────────────────────

def parse_critique(raw: str) -> dict:
    """
    Extract structured JSON from critic response.
    Tries direct parse first, then searches for {...} block within prose.
    Returns dict with keys: confidence, approved, issues, praise, summary.
    Raises ValueError if no valid JSON found.
    """
    # Direct parse
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Find JSON block in prose
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass

    raise ValueError("No valid JSON found in critic response")


def _safe_parse_critique(raw: str, critic_id: str) -> Optional[dict]:
    """
    Parse critique with one retry if initial parse fails.
    Uses ask_model_isolated to re-ask the critic for valid JSON.
    """
    try:
        return parse_critique(raw)
    except ValueError:
        print_warn("Critic returned non-JSON. Retrying...")
        retry_prompt = (
            f"{CRITIC_SYSTEM}\n\n[TASK]\n"
            "Your previous response was not valid JSON. "
            "Respond ONLY with the JSON object — no explanation, no markdown fences."
        )
        retry_raw = ask_model_isolated(retry_prompt, critic_id)
        try:
            return parse_critique(retry_raw)
        except ValueError:
            print_warn("Retry also failed. Using fallback critique.")
            return {
                "confidence": 50,
                "approved": False,
                "issues": [{
                    "severity": "major",
                    "location": "review",
                    "problem": "Critic returned unparseable response",
                    "suggestion": "Check critic model output format"
                }],
                "praise": "N/A",
                "summary": "Critique could not be parsed. Continuing with fallback."
            }


# ── Critique Formatter ────────────────────────────────────────────────────────

def format_critique_for_planner(critique: dict, iteration: int) -> str:
    """Convert structured critique into a clear revision prompt for the planner."""
    issues = critique.get("issues", [])

    issue_lines = ""
    for i, issue in enumerate(issues, 1):
        icon = {"critical": "🔴", "major": "🟡", "minor": "🟢"}.get(
            issue.get("severity", "minor"), "⚪"
        )
        issue_lines += (
            f"\n{icon} Issue {i} [{issue.get('severity', '?').upper()}]"
            f" — {issue.get('location', 'unspecified')}\n"
            f"   Problem    : {issue.get('problem', '')}\n"
            f"   Fix needed : {issue.get('suggestion', '')}\n"
        )

    return (
        f"REVIEW REPORT (Iteration {iteration})\n"
        f"{'='*52}\n"
        f"Confidence : {critique.get('confidence', '?')}/100\n"
        f"What works : {critique.get('praise', 'N/A')}\n"
        f"Assessment : {critique.get('summary', '')}\n"
        f"\nISSUES TO ADDRESS:{issue_lines if issue_lines else chr(10) + '  None critical — tighten where possible.'}\n"
        f"{'='*52}\n\n"
        f"Revise the FULL plan addressing all issues above."
    )


# ── Display Helpers ───────────────────────────────────────────────────────────

SEVERITY_ICON = {"critical": "🔴", "major": "🟡", "minor": "🟢"}

def _confidence_badge(score: int) -> str:
    if score >= 85:
        return f"🟢 {score}/100"
    elif score >= 50:
        return f"🟡 {score}/100"
    return f"🔴 {score}/100"


def _render_plan(plan: str, version: int, planner_id: str) -> None:
    if HAS_RICH:
        console.print(Panel(
            plan,
            title=f"[bold cyan]📝 Plan v{version}[/bold cyan]  [dim]{planner_id}[/dim]",
            border_style="cyan",
            padding=(1, 2)
        ))
    else:
        print(f"\n{'─'*60}")
        print(f"📝 Plan v{version} ({planner_id})")
        print(f"{'─'*60}")
        print(plan)
        print(f"{'─'*60}\n")


def _render_critique(critique: dict, iteration: int, critic_id: str) -> None:
    issues = critique.get("issues", [])
    confidence = critique.get("confidence", 0)
    approved = critique.get("approved", False)

    if HAS_RICH:
        content = Text()
        content.append(f"Confidence : {_confidence_badge(confidence)}\n")
        content.append(
            f"Status     : {'✅ APPROVED' if approved else '❌ Needs revision'}\n"
        )
        content.append(f"Summary    : {critique.get('summary', '')}\n")
        content.append(f"Praise     : {critique.get('praise', '')}\n")

        if issues:
            content.append(f"\nIssues ({len(issues)}):\n", style="bold")
            for issue in issues:
                icon = SEVERITY_ICON.get(issue.get("severity", "minor"), "⚪")
                content.append(
                    f"  {icon} [{issue.get('severity', '?')}] "
                    f"{issue.get('location', '')} — "
                    f"{issue.get('problem', '')}\n"
                )
        else:
            content.append("\n  No issues raised.\n")

        console.print(Panel(
            content,
            title=f"[bold yellow]🔍 Critique #{iteration}[/bold yellow]  [dim]{critic_id}[/dim]",
            border_style="yellow",
            padding=(1, 2)
        ))
    else:
        print(f"\n{'─'*60}")
        print(f"🔍 Critique #{iteration} ({critic_id})")
        print(f"  Confidence: {confidence}/100  |  {'APPROVED' if approved else 'Needs revision'}")
        print(f"  Summary: {critique.get('summary', '')}")
        for issue in issues:
            icon = SEVERITY_ICON.get(issue.get("severity", "minor"), "⚪")
            print(f"  {icon} [{issue.get('severity', '?')}] {issue.get('location', '')} — {issue.get('problem', '')}")
        print(f"{'─'*60}\n")


def _render_final(plan: str, stats: dict) -> None:
    if HAS_RICH:
        console.print(Panel(
            plan,
            title="[bold green]✅ Final Approved Plan[/bold green]",
            border_style="green",
            box=box.DOUBLE,
            padding=(1, 2)
        ))
        console.print(
            f"[dim]  Iterations: {stats['iterations']}  |  "
            f"Final confidence: {stats['final_confidence']}/100  |  "
            f"Issues raised: {stats['issues_raised']}  |  "
            f"Approved: {'✅' if stats['approved'] else '⚠️ best-effort'}[/dim]\n"
        )
    else:
        print(f"\n{'═'*60}")
        print(f"✅ FINAL PLAN")
        print(f"{'═'*60}")
        print(plan)
        print(f"{'═'*60}")
        print(f"  Iterations: {stats['iterations']} | Confidence: {stats['final_confidence']}/100 | "
              f"Approved: {'Yes' if stats['approved'] else 'Best-effort'}\n")


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run_collab(raw_args: str, free_models: list[dict]) -> None:
    """
    Synchronous Critic-Refiner loop. Called from main.py dispatch block.

    Args:
        raw_args    : everything after '/collab'
        free_models : list of available model dicts
    """
    # ── Parse args ──
    topic, max_rounds, threshold, swap = _parse_collab_args(raw_args)

    if not topic:
        print_error("Usage: /collab <topic> [--rounds N] [--threshold N] [--swap]")
        return

    # ── Pick models ──
    planner, critic = _pick_collab_models(free_models)
    if planner is None or critic is None:
        return

    planner_id = planner["id"]
    critic_id = critic["id"]

    # ── Session banner ──
    if HAS_RICH:
        banner = (
            f"[bold]Topic[/bold]     : {topic}\n"
            f"[bold]Planner[/bold]   : {planner_id}\n"
            f"[bold]Critic[/bold]    : {critic_id}\n"
            f"[bold]Max rounds[/bold]: {max_rounds}  |  "
            f"[bold]Threshold[/bold]: {threshold}%"
            + ("  |  [bold]Role-swap ON[/bold]" if swap else "")
        )
        console.print(Panel(
            banner,
            title="[bold green]🤝 COLLAB SESSION[/bold green]",
            border_style="green",
            box=box.DOUBLE,
            padding=(1, 2)
        ))
    else:
        print(f"\n🤝 COLLAB SESSION")
        print(f"   Topic:     {topic}")
        print(f"   Planner:   {planner_id}")
        print(f"   Critic:    {critic_id}")
        print(f"   Max rounds: {max_rounds} | Threshold: {threshold}%"
              + (" | Role-swap ON" if swap else ""))
        print()

    iteration = 0
    current_plan = ""
    last_critique: Optional[dict] = None
    total_issues_raised = 0

    # ── Initial plan ──
    initial_prompt = (
        f"Create a detailed, well-structured plan for the following:\n\n{topic}"
    )
    full_prompt = f"{PLANNER_SYSTEM}\n\n[TASK]\n{initial_prompt}"

    with ThinkingSpinner([f"[Planner: {planner_id}] Generating initial plan..."]):
        response = ask_model_isolated(full_prompt, planner_id)

    if not response or response.startswith("Error:") or response.startswith("API Error:"):
        print_error(f"Planner failed: {response}")
        return

    current_plan = response
    _render_plan(current_plan, version=1, planner_id=planner_id)

    # ── Critique-Refine Loop ──
    while iteration < max_rounds:
        iteration += 1

        # Optional role-swap at midpoint
        if swap and iteration == (max_rounds // 2) + 1:
            planner_id, critic_id = critic_id, planner_id
            if HAS_RICH:
                console.print(
                    f"[bold magenta]🔄 Role swap! "
                    f"Planner → {planner_id} | Critic → {critic_id}[/bold magenta]\n"
                )
            else:
                print(f"🔄 Role swap! Planner → {planner_id} | Critic → {critic_id}\n")

        # ── Critic reviews current plan ──
        critic_task = (
            f"Review this plan for: '{topic}'\n\n"
            f"--- PLAN ---\n{current_plan}\n--- END PLAN ---\n\n"
            "Provide your structured JSON critique."
        )
        critic_full_prompt = f"{CRITIC_SYSTEM}\n\n[TASK]\n{critic_task}"

        with ThinkingSpinner(
            [f"[Critic: {critic_id}] Reviewing plan (round {iteration}/{max_rounds})..."]
        ):
            raw_critique = ask_model_isolated(critic_full_prompt, critic_id)

        if not raw_critique or raw_critique.startswith("Error:") or raw_critique.startswith("API Error:"):
            print_warn(f"Critic API error: {raw_critique}. Skipping round.")
            continue

        # Parse with retry
        critique = _safe_parse_critique(raw_critique, critic_id)
        if critique is None:
            print_error("Could not parse critique. Aborting.")
            break

        last_critique = critique

        # Track issues for stats
        total_issues_raised += len(critique.get("issues", []))

        _render_critique(critique, iteration=iteration, critic_id=critic_id)

        confidence = critique.get("confidence", 0)
        approved = critique.get("approved", False)

        # ── Convergence check ──
        if approved or confidence >= threshold:
            if HAS_RICH:
                console.print(
                    f"[bold green]✅ Approved after {iteration} round(s)! "
                    f"Confidence: {confidence}/100[/bold green]\n"
                )
            else:
                print(f"✅ Approved after {iteration} round(s)! Confidence: {confidence}/100\n")
            break

        if iteration == max_rounds:
            print_warn(
                f"Max rounds ({max_rounds}) reached. "
                f"Returning best plan (confidence: {confidence}/100)."
            )
            break

        # ── Planner revises ──
        revision_prompt = format_critique_for_planner(critique, iteration)
        planner_full_prompt = f"{PLANNER_SYSTEM}\n\n{revision_prompt}"

        with ThinkingSpinner(
            [f"[Planner: {planner_id}] Revising plan (round {iteration})..."]
        ):
            revised = ask_model_isolated(planner_full_prompt, planner_id)

        if not revised or revised.startswith("Error:") or revised.startswith("API Error:"):
            print_warn(f"Planner revision failed: {revised}. Stopping.")
            break

        current_plan = revised
        _render_plan(current_plan, version=iteration + 1, planner_id=planner_id)

    # ── Final Output ──
    stats = {
        "iterations": iteration,
        "final_confidence": last_critique.get("confidence", 0) if last_critique else 0,
        "approved": last_critique.get("approved", False) if last_critique else False,
        "issues_raised": total_issues_raised,
    }

    _render_final(current_plan, stats)

    # ── Save to session conversation ──
    session_summary = (
        f"## Collab: {topic}\n\n"
        f"{current_plan}\n\n"
        f"## Session Stats\n"
        f"- Iterations: {stats['iterations']}\n"
        f"- Final confidence: {stats['final_confidence']}/100\n"
        f"- Approved: {'Yes' if stats['approved'] else 'No (best-effort)'}\n"
        f"- Total issues raised: {stats['issues_raised']}\n"
        f"- Planner: {planner_id} | Critic: {critic_id}\n"
    )

    state.conversation.append({"role": "user", "content": f"/collab {topic}"})
    state.conversation.append({"role": "assistant", "content": session_summary})
