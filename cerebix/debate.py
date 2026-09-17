import os
import re
import time
from . import state
from .config import print_error, print_warn, print_info, print_success, HAS_RICH, console
from .models import display_model_table, format_ctx
from .api import ask_model_isolated
from .routing import _pick_by_context
from .spinner import _thinking_spinner, _DEBATE_MESSAGES, _JUDGE_MESSAGES

if HAS_RICH:
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich import box


DEBATE_STYLES = {
    "standard": "Be sharp, analytical, and structured. Use empirical examples, analogies, and formal debate logic. Keep responses under 180 words.",
    "savage": "Be ruthlessly critical, sharp, and witty. Call out logical fallacies and flaws in your opponent's arguments directly by name. Zero fluff, high impact. Keep responses under 180 words.",
    "dramatic": "Be theatrical and expressive. Use vivid metaphors, express theatrical skepticism or disbelief at your opponent's arguments. Keep responses under 180 words.",
    "academic": "Use formal academic terminology, citing theoretical frameworks, edge cases, and principles. Treat this as rigorous peer review. Keep responses under 180 words.",
}

DEBATER_BASE_SYSTEM = """\
You are a championship debater representing your assigned stance in an adversarial multi-round debate.

Style Guidelines:
{style_guideline}

Your Assigned Position:
{assigned_position}

Rules:
1. Strongly defend your assigned stance with compelling arguments and concrete examples.
2. In rounds 2 and beyond, directly quote and dismantle your opponent's specific claims.
3. Never break character, never hedge into neutrality, and never switch sides.
4. Keep your output concise and punchy (under 180 words). Output ONLY your debate speech."""

JUDGE_SYSTEM = """\
You are an impartial Chief Justice and debate adjudicator evaluating an adversarial debate between two AI models.
Your task:
1. Evaluate the arguments presented in each round based on logic, evidence, rebuttal effectiveness, and persuasiveness under pressure.
2. Highlight the most decisive arguments and rebuttals from each side.
3. Declare a definitive WINNER with clear justification (do not call a tie).
4. Provide a structured scorecard.

Format your verdict in clean markdown:
- **Debate Overview**: Brief summary of the clash.
- **Round-by-Round Breakdown**:
  - Round 1 (Opening Arguments): Key points from Affirmative vs Negative.
  - Subsequent Rounds: Decisive rebuttals and turning points.
- **Scorecard**:
  - Affirmative ({pro_name}): Logic: X/10 | Rebuttal: Y/10 | Persuasiveness: Z/10
  - Negative ({con_name}): Logic: X/10 | Rebuttal: Y/10 | Persuasiveness: Z/10
- **Winner Declaration**: Clear winner and rationale."""


def _parse_debate_args(raw_text):
    """Parse topic, optional --style, and optional --rounds from input string."""
    style = "standard"
    rounds = 3
    parts = raw_text.split()
    topic_tokens = []
    i = 0
    while i < len(parts):
        if parts[i] == "--style" and i + 1 < len(parts):
            s = parts[i + 1].lower().strip()
            if s in DEBATE_STYLES:
                style = s
            i += 2
        elif parts[i] == "--rounds" and i + 1 < len(parts):
            try:
                rounds = max(2, min(4, int(parts[i + 1])))
            except ValueError:
                pass
            i += 2
        else:
            topic_tokens.append(parts[i])
            i += 1

    topic = " ".join(topic_tokens).strip("\"' ")
    return topic, style, rounds


def _pick_debaters_interactive(free_models):
    """Interactively choose two debater models and a judge model."""
    display_model_table(free_models, title="Select Debate Competitors")

    print_info("\nPick 2 debater model numbers (comma-separated, e.g. '1, 4')")
    print_info("  [Press Enter for auto: Current Model vs Top Challenger]")

    while True:
        try:
            choice = input("\nDebaters: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None, None, None

        if not choice:
            # Auto-selection: current model + top alternative
            pro = state.current_model or free_models[0]
            con = next((m for m in free_models if m["id"] != pro["id"]), free_models[-1])
            break

        try:
            indices = [int(x.strip()) for x in choice.split(",")]
            selected = [free_models[i] for i in indices if 0 <= i < len(free_models)]
            if len(selected) != 2:
                print_error("Please pick exactly 2 models (e.g. '2, 5').")
                continue
            pro, con = selected[0], selected[1]
            break
        except (ValueError, IndexError):
            print_error("Invalid selection. Use comma-separated numbers (e.g. '0, 3').")

    # Pick judge: defaults to the largest-context reasoning model
    default_judge = _pick_by_context(free_models, exclude_weak=True) or pro
    print_info(f"\nDefault Judge: {default_judge['name']} ({format_ctx(default_judge.get('context', 0))})")
    print_info("  (Press Enter to accept default, or type a model number)")

    try:
        j_choice = input("Judge: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None, None, None

    if j_choice and j_choice.isdigit() and 0 <= int(j_choice) < len(free_models):
        judge = free_models[int(j_choice)]
    else:
        judge = default_judge

    return pro, con, judge


def run_debate(raw_args, free_models):
    """Orchestrate an adversarial multi-round debate with stance forcing and judicial verdict."""
    topic, style, rounds = _parse_debate_args(raw_args)
    if not topic:
        print_error("Please provide a topic. Usage: /debate <topic> [--style standard|savage|dramatic|academic] [--rounds 2-4]")
        return

    if len(free_models) < 2:
        print_error("Need at least 2 free models available to run a debate.")
        return

    pro_model, con_model, judge_model = _pick_debaters_interactive(free_models)
    if not pro_model or not con_model or not judge_model:
        print_warn("Debate cancelled.")
        return

    style_desc = DEBATE_STYLES.get(style, DEBATE_STYLES["standard"])

    pro_system = DEBATER_BASE_SYSTEM.format(
        style_guideline=style_desc,
        assigned_position=f"You MUST argue the AFFIRMATIVE (PRO) stance FOR: '{topic}'. You believe this strongly and must defend it passionately.",
    )
    con_system = DEBATER_BASE_SYSTEM.format(
        style_guideline=style_desc,
        assigned_position=f"You MUST argue the NEGATIVE (CON) stance AGAINST: '{topic}'. You oppose this and must dismantle the affirmative case.",
    )

    # Title Banner
    if HAS_RICH:
        console.print()
        console.print(Panel(
            f"[bold white]Topic:[/] [cyan]{topic}[/]\n"
            f"[bold white]Format:[/] {rounds} Rounds • Style: [bold yellow]{style.upper()}[/]\n\n"
            f"[bold cyan]🔵 AFFIRMATIVE (PRO):[/] {pro_model['name']}\n"
            f"[bold magenta]🟣 NEGATIVE (CON):[/] {con_model['name']}\n"
            f"[bold yellow]⚖️  JUDGE:[/] {judge_model['name']}",
            title="[bold green]🥊 CEREBIX AI ARENA — MULTI-AGENT DEBATE[/]",
            border_style="green",
            box=box.DOUBLE,
        ))
    else:
        print(f"\n=== 🥊 CEREBIX DEBATE: {topic} ===")
        print(f"Format: {rounds} Rounds | Style: {style}")
        print(f"PRO: {pro_model['name']} | CON: {con_model['name']} | Judge: {judge_model['name']}\n")

    transcript_entries = []
    pro_prev = ""
    con_prev = ""

    ROUND_NAMES = {
        1: "Opening Arguments",
        2: "Rebuttal & Cross-Examination",
        3: "Counter-Rebuttal & Clashes",
        4: "Closing Statements",
    }

    for r in range(1, rounds + 1):
        round_name = ROUND_NAMES.get(r, f"Round {r}")
        print_info(f"\n{'='*55}\n  ROUND {r}: {round_name.upper()}\n{'='*55}")

        # Pro Turn
        if r == 1:
            pro_prompt = f"The debate topic is: '{topic}'.\nPresent your opening argument advocating for the AFFIRMATIVE position."
        elif r == rounds:
            pro_prompt = (
                f"Topic: '{topic}'. This is the FINAL ROUND.\n"
                f"Your opponent (Negative) argued:\n\"{con_prev}\"\n\n"
                f"Deliver your closing stand. Rebut their final attacks and summarize why the Affirmative stance wins."
            )
        else:
            pro_prompt = (
                f"Topic: '{topic}'. Round {r}.\n"
                f"Your opponent (Negative) argued:\n\"{con_prev}\"\n\n"
                f"Directly quote and dismantle their points, and reinforce your Affirmative stance."
            )

        print_info(f"🔵 {pro_model['name']} is preparing speech...")
        with _thinking_spinner(_DEBATE_MESSAGES):
            pro_speech = ask_model_isolated(
                f"{pro_system}\n\n[USER INSTRUCTION]\n{pro_prompt}",
                pro_model["id"]
            )
        pro_prev = pro_speech.strip()
        transcript_entries.append((r, "PRO", pro_model["name"], pro_prev))

        if HAS_RICH:
            console.print(Panel(
                Markdown(pro_prev),
                title=f"[bold cyan]🔵 PRO (Affirmative): {pro_model['name']} — Round {r}[/]",
                border_style="cyan",
                box=box.ROUNDED,
            ))
        else:
            print(f"\n--- 🔵 PRO ({pro_model['name']}) ---\n{pro_prev}")

        time.sleep(0.5)

        # Con Turn
        if r == 1:
            con_prompt = (
                f"The debate topic is: '{topic}'.\n"
                f"Your opponent (Affirmative) opened with:\n\"{pro_prev}\"\n\n"
                f"Present your opening argument advocating for the NEGATIVE position, directly challenging their initial claims."
            )
        elif r == rounds:
            con_prompt = (
                f"Topic: '{topic}'. This is the FINAL ROUND.\n"
                f"Your opponent (Affirmative) argued:\n\"{pro_prev}\"\n\n"
                f"Deliver your closing stand. Rebut their points and summarize why the Negative stance wins."
            )
        else:
            con_prompt = (
                f"Topic: '{topic}'. Round {r}.\n"
                f"Your opponent (Affirmative) argued:\n\"{pro_prev}\"\n\n"
                f"Directly quote and dismantle their points, and reinforce your Negative stance."
            )

        print_info(f"🟣 {con_model['name']} is preparing speech...")
        with _thinking_spinner(_DEBATE_MESSAGES):
            con_speech = ask_model_isolated(
                f"{con_system}\n\n[USER INSTRUCTION]\n{con_prompt}",
                con_model["id"]
            )
        con_prev = con_speech.strip()
        transcript_entries.append((r, "CON", con_model["name"], con_prev))

        if HAS_RICH:
            console.print(Panel(
                Markdown(con_prev),
                title=f"[bold magenta]🟣 CON (Negative): {con_model['name']} — Round {r}[/]",
                border_style="magenta",
                box=box.ROUNDED,
            ))
        else:
            print(f"\n--- 🟣 CON ({con_model['name']}) ---\n{con_prev}")

        time.sleep(0.5)

    # Judge Phase
    print_info(f"\n{'='*55}\n  ⚖️  CHIEF JUSTICE ADJUDICATION\n{'='*55}")
    print_info(f"Delivering full debate transcript to {judge_model['name']} for verdict...")

    full_transcript = f"# Debate Topic: {topic}\n\n"
    for r, side, mname, speech in transcript_entries:
        full_transcript += f"### Round {r} — [{side}] {mname}\n{speech}\n\n"

    judge_prompt = (
        f"{JUDGE_SYSTEM.format(pro_name=pro_model['name'], con_name=con_model['name'])}\n\n"
        f"--- DEBATE TRANSCRIPT ---\n\n"
        f"{full_transcript}\n"
        f"Deliver your comprehensive evaluation, scores, and winner declaration now:"
    )

    with _thinking_spinner(_JUDGE_MESSAGES):
        verdict = ask_model_isolated(judge_prompt, judge_model["id"])

    if HAS_RICH:
        console.print()
        console.print(Panel(
            Markdown(verdict),
            title=f"[bold yellow]⚖️  JUDGE'S FINAL VERDICT — {judge_model['name']}[/]",
            border_style="yellow",
            box=box.DOUBLE,
        ))
    else:
        print(f"\n=== ⚖️ JUDGE'S VERDICT ===\n{verdict}")

    # Save to session conversation
    state.conversation.append({"role": "user", "content": f"/debate {topic}"})
    state.conversation.append({
        "role": "assistant",
        "content": f"## Debate: {topic}\n\n{full_transcript}\n\n## Verdict\n{verdict}"
    })
    print_success("Debate complete! Full transcript saved to active conversation.")
