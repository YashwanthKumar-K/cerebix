import json
import re
import time
import os
import requests
from datetime import datetime
from .config import print_error, print_warn, print_info, HEADERS, HAS_RICH, console
from .spinner import _thinking_spinner, _PLAN_MESSAGES, _CODE_MESSAGES
from .routing import _heuristic_pick, _pick_by_context
from .models import choose_model
if HAS_RICH:
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

# Internal founder-level system prompt that structures how the model plans
_PLANNER_SYSTEM = """\
You are Cerebix Project Architect — a senior software engineer who designs clean, \
modular, production-ready project structures.

When asked to plan a project you MUST respond with ONLY valid JSON — no explanation, \
no markdown fences, no preamble. The JSON must strictly follow this schema:

{
  "project_name": "<slug-name, lowercase, hyphens only>",
  "description": "<one sentence summary>",
  "tech_stack": ["<technology>", ...],
  "files": [
    {
      "path": "<relative/path/to/file.ext>",
      "description": "<what this file does and what it must export/define>",
      "dependencies": ["<other file paths this file imports from>"]
    }
  ]
}

Rules:
- Start with entry point files first (e.g. main.py, app.py, index.html).
- Keep files small and single-purpose (150 lines each ideally).
- List EVERY file needed to run the project — no placeholders.
- The description must be specific enough that a developer can write the file from it alone.
- Maximum 15 files for a focused, working project.
"""

_FILE_SYSTEM = """\
You are Cerebix Code Generator. You write production-quality code for a specific file \
inside a larger project. You MUST:
- Output ONLY the raw file content — no markdown fences, no explanation before or after.
- Make sure every import statement is correct relative to the project file structure provided.
- Every function/class mentioned in the file description MUST be implemented.
- Include brief inline comments for non-obvious logic.
- The code must be complete and runnable — no TODO stubs, no placeholder functions.
"""


def _extract_json(text):
    """Robustly pull JSON from model output even if wrapped in markdown or prose."""
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass
    brace_match = re.search(r"\{[\s\S]+\}", text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _validate_plan(plan):
    """Ensure the plan JSON is structurally valid and safe before execution."""
    if not isinstance(plan, dict):
        print_error("Plan is not a valid JSON object.")
        return False
    if "project_name" not in plan or not isinstance(plan["project_name"], str):
        print_error("Plan is missing a valid 'project_name'.")
        return False
        
    files = plan.get("files")
    if not isinstance(files, list):
        print_error("Plan is missing a valid 'files' list.")
        return False
    if len(files) == 0 or len(files) > 15:
        print_error(f"Plan validation failed: file count {len(files)} not in range 1-15.")
        return False
        
    seen_paths = set()
    for f in files:
        if not isinstance(f, dict):
            print_error("A file entry is not a valid JSON object.")
            return False
        path = f.get("path")
        desc = f.get("description")
        if not path or not desc or not isinstance(path, str) or not isinstance(desc, str):
            print_error("A file entry is missing 'path' or 'description'.")
            return False
        if path in seen_paths:
            print_error(f"Plan validation failed: duplicate path '{path}'.")
            return False
        seen_paths.add(path)
    return True


def _plan_project(description, model_id):
    """Phase 1 — Ask the model to plan the project structure as JSON."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    messages = [
        {"role": "system", "content": _PLANNER_SYSTEM},
        {"role": "user", "content": f"Plan this project:\n\n{description}"},
    ]
    payload = {"model": model_id, "messages": messages}

    print_info("Phase 1 — Planning project structure...")
    backoff = [5, 15, 30]
    resp = None
    with _thinking_spinner(_PLAN_MESSAGES):
        for attempt in range(len(backoff) + 1):
            try:
                resp = requests.post(url, headers=HEADERS, json=payload, timeout=90)
                if resp.status_code == 429:
                    if attempt < len(backoff):
                        time.sleep(backoff[attempt])
                        continue
                    resp = None
                    break
                if resp.status_code != 200:
                    resp = None
                    break
                break
            except requests.RequestException:
                if attempt < len(backoff):
                    time.sleep(backoff[attempt])
                    continue
                resp = None
                break

    if resp is None:
        print_error("Planning phase: API call failed (rate limit or network error).")
        return None
    if resp.status_code != 200:
        try:
            msg = resp.json().get("error", {}).get("message", resp.text[:200])
        except Exception:
            msg = resp.text[:200]
        print_error(f"API Error ({resp.status_code}): {msg}")
        return None

    choices = resp.json().get("choices", [])
    if not choices:
        print_error("Model returned empty response during planning.")
        return None

    raw = choices[0].get("message", {}).get("content", "")
    plan = _extract_json(raw)
    if not plan or not _validate_plan(plan):
        print_error("Could not parse or validate project plan JSON from model response.")
        if HAS_RICH:
            console.print(Panel(raw[:2000], title="[red]Raw Model Output[/]", border_style="red"))
        else:
            print(f"\n--- Raw output (first 2000 chars) ---\n{raw[:2000]}")
        print_warn("Tip: Try a stronger model via /select (e.g. Nemotron Ultra), then /build again.")
        return None
    return plan


def _generate_file(file_info, plan, model_id):
    """Phase 2 — Generate content for one specific file."""
    url = "https://openrouter.ai/api/v1/chat/completions"

    file_manifest = "\n".join(
        f"  {f['path']} -- {f['description']}"
        for f in plan.get("files", [])
    )

    user_prompt = (
        f"Project: {plan.get('project_name', 'project')}\n"
        f"Tech stack: {', '.join(plan.get('tech_stack', []))}\n\n"
        f"Project file manifest (for correct import paths):\n{file_manifest}\n\n"
        f"NOW WRITE THE FILE: {file_info['path']}\n"
        f"Purpose: {file_info['description']}\n"
        f"This file imports from: {', '.join(file_info.get('dependencies', [])) or 'none'}\n\n"
        f"Output ONLY the raw file content. No fences, no explanation."
    )

    messages = [
        {"role": "system", "content": _FILE_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]
    payload = {"model": model_id, "messages": messages}

    backoff = [5, 15, 30]
    resp = None
    for attempt in range(len(backoff) + 1):
        try:
            resp = requests.post(url, headers=HEADERS, json=payload, timeout=90)
            if resp.status_code == 429:
                if attempt < len(backoff):
                    print_warn(f"  Rate limited. Waiting {backoff[attempt]}s...")
                    time.sleep(backoff[attempt])
                    continue
                return None
            if resp.status_code != 200:
                return None
            break
        except requests.RequestException:
            if attempt < len(backoff):
                time.sleep(backoff[attempt])
                continue
            return None

    if resp is None:
        return None

    choices = resp.json().get("choices", [])
    if not choices:
        return None

    content = choices[0].get("message", {}).get("content", "")
    # Strip accidental markdown fences the model may add despite instructions
    fence = re.match(r"^```[\w]*\n([\s\S]+?)\n```$", content.strip())
    if fence:
        content = fence.group(1)
    return content.strip()


def _display_plan(plan):
    """Show the project plan as a table before execution."""
    files = plan.get("files", [])
    if HAS_RICH:
        table = Table(
            title=f"[bold cyan]{plan.get('project_name', 'Project')} — File Plan[/]",
            box=box.ROUNDED,
            show_lines=True,
        )
        table.add_column("#",    style="bold cyan", justify="right", width=3)
        table.add_column("File", style="bold white")
        table.add_column("Purpose", style="dim")
        table.add_column("Deps", style="yellow", justify="center", width=5)
        for i, f in enumerate(files, 1):
            dep_count = len(f.get("dependencies", []))
            desc = f["description"]
            table.add_row(
                str(i),
                f["path"],
                desc[:72] + ("..." if len(desc) > 72 else ""),
                str(dep_count) if dep_count else "-",
            )
        console.print()
        console.print(Panel.fit(
            f"[bold white]{plan.get('description', '')}[/]\n"
            f"[dim]Stack: {', '.join(plan.get('tech_stack', []))}[/]",
            title=f"[bold cyan]{plan.get('project_name')}[/]",
            border_style="cyan",
        ))
        console.print(table)
    else:
        print(f"\n=== Project: {plan.get('project_name')} ===")
        print(f"  {plan.get('description')}")
        print(f"  Stack: {', '.join(plan.get('tech_stack', []))}")
        print(f"\n  Files ({len(files)}):")
        for i, f in enumerate(files, 1):
            print(f"  [{i}] {f['path']} -- {f['description'][:60]}...")


def run_project_build(description, free_models):
    """
    /build orchestrator — 3 phases:
      Phase 1: Model outputs a JSON project plan.
      Phase 2: Generate each file with full project context.
      Phase 3: Write everything to disk.
    """
    if not description.strip():
        print_error("Usage: /build <what you want to build> [--generator <model_id>]")
        print_info("  Example: /build A Flask REST API with user login and a SQLite database")
        return

    # Parse --generator flag if present
    custom_generator_id = None
    if "--generator" in description:
        parts = description.split("--generator")
        description = parts[0].strip()
        if len(parts) > 1:
            custom_generator_id = parts[1].strip().split()[0]

    # Prefer strongest reasoning model for planning (never pick nano/tiny models)
    pick = _heuristic_pick("reasoning", free_models, exclude_weak=True)
    planner_model = pick or _pick_by_context(free_models, exclude_weak=True)
    print_info(f"Architect: {planner_model['name']}")

    # ---- Phase 1: Plan ----
    plan = _plan_project(description, planner_model["id"])
    if not plan or not plan.get("files"):
        print_error("Planning phase failed. Try /select to pick a stronger model, then /build again.")
        return

    _display_plan(plan)

    # ---- Confirm ----
    file_count = len(plan.get("files", []))
    try:
        confirm = input(
            f"\nGenerate {file_count} file(s)? (This sends {file_count} API calls) [y/n]: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if confirm != "y":
        print_warn("Cancelled.")
        return

    project_name = plan.get("project_name", "cerebix-project")

    # ---- Generator Loop (Phases 2 & 3) ----
    while True:
        # Determine generator model
        if custom_generator_id:
            generator_model = next((m for m in free_models if m["id"] == custom_generator_id), None)
            if not generator_model:
                print_warn(f"Model '{custom_generator_id}' not found. Falling back to default.")
                custom_generator_id = None
                
        if not custom_generator_id:
            # Ranked priority list of known good free code generators
            # We iterate through this list to find the first one available
            PREFERRED_GENERATORS = [
                "nemotron-3-ultra",        # 1M ctx, largest reasoning
                "glm-5.2",                 # 256K ctx, strong code benchmark
                "nemotron-3-super",        # Good fallback if Ultra is rate-limited
                "minimax-m3",              # 1M ctx, decent capability
                "north-mini-code",         # Code-specific but mini
                "nemotron-3.5-lightning",  # Fast, 1M ctx
                "gemma-4-31b",             # Solid general
                "gemma-4-26b"              # Smaller sibling
            ]
            
            generator_model = None
            for pref in PREFERRED_GENERATORS:
                match = next((m for m in free_models if pref in m["id"].lower()), None)
                if match:
                    generator_model = match
                    break
            
            if not generator_model:
                # Absolute fallback if none of our preferred models are currently free
                gen_pick = _heuristic_pick("code", free_models, exclude_weak=False)
                if gen_pick and gen_pick["id"] != planner_model["id"]:
                    generator_model = gen_pick
                else:
                    generator_model = planner_model

        print_info(f"\nGenerator: {generator_model['name']}")

        # ---- Output directory ----
        default_dir = os.path.join(os.getcwd(), project_name)
        print_info(f"Where should the project be saved?")
        print_info(f"  Default: {default_dir}")
        print_info(f"  (Press Enter to use default, or type a custom path)")
        try:
            out_dir_input = input("Output path: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        out_dir = out_dir_input if out_dir_input else default_dir

        # ---- Phase 2: Generate files ----
        print_info(f"\nPhase 2 — Generating {file_count} file(s)...")
        generated = {}
        failed = []

        for i, file_info in enumerate(plan["files"], 1):
            fpath = file_info["path"]
            if HAS_RICH:
                console.print(f"\n  [dim]({i}/{file_count})[/] [bold white]{fpath}[/]")
            else:
                print(f"\n  ({i}/{file_count}) {fpath}")

            with _thinking_spinner(_CODE_MESSAGES):
                content = _generate_file(file_info, plan, generator_model["id"])

            if content:
                generated[fpath] = content
                if HAS_RICH:
                    console.print(f"  [bold green][OK][/] {fpath}")
                else:
                    print(f"  [OK] {fpath}")
            else:
                failed.append(fpath)
                if HAS_RICH:
                    console.print(f"  [bold red][FAILED][/] {fpath}")
                else:
                    print(f"  [FAILED] {fpath}")

        # ---- Phase 3: Write to disk ----
        print_info(f"\nPhase 3 — Writing to {out_dir}...")
        written = []

        def safe_join_output_path(base_dir, relative_path):
            """Ensure the generated path cannot escape the base_dir (prevents ../ traversal)."""
            # Strip leading slashes to prevent absolute path evaluation
            clean_rel = relative_path.lstrip("\\/")
            final_path = os.path.abspath(os.path.join(base_dir, clean_rel))
            base_dir_abs = os.path.abspath(base_dir)
            if not final_path.startswith(base_dir_abs + os.sep) and final_path != base_dir_abs:
                return None
            return final_path

        for fpath, content in generated.items():
            full_path = safe_join_output_path(out_dir, fpath)
            if not full_path:
                print_error(f"Security: Rejected unsafe path '{fpath}'")
                failed.append(fpath)
                continue
            
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            try:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                written.append(fpath)
            except OSError as e:
                print_error(f"Could not write {fpath}: {e}")
                failed.append(fpath)

        # Write build manifest
        manifest_path = os.path.join(out_dir, "CEREBIX_BUILD.md")
        try:
            with open(manifest_path, "w", encoding="utf-8") as mf:
                mf.write(f"# {plan.get('project_name')}\n\n")
                mf.write(f"{plan.get('description', '')}\n\n")
                mf.write(f"**Tech Stack:** {', '.join(plan.get('tech_stack', []))}\n\n")
                mf.write(f"**Architect Model:** {planner_model['name']} (`{planner_model['id']}`)\n")
                mf.write(f"**Generator Model:** {generator_model['name']} (`{generator_model['id']}`)\n\n")
                mf.write("## Generated Files\n\n")
                for fi in plan["files"]:
                    status = "[v]" if fi["path"] in written else "[FAILED]"
                    mf.write(f"- {status} `{fi['path']}` — {fi['description']}\n")
                mf.write(f"\n*Built by Cerebix on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
        except OSError:
            pass

        # ---- Summary ----
        if HAS_RICH:
            console.print()
            summary = f"[bold green]{len(written)} file(s) written[/] to [cyan]{out_dir}[/]\n"
            if failed:
                summary += f"[bold red]{len(failed)} failed:[/] {', '.join(failed)}\n"
            summary += f"[dim]Build manifest: CEREBIX_BUILD.md[/]"
            console.print(Panel(
                summary,
                title="[bold cyan]Build Complete[/]",
                border_style="cyan",
                box=box.ROUNDED,
            ))
        else:
            print(f"\n[v] {len(written)} file(s) written to {out_dir}")
            if failed:
                print(f"[x] {len(failed)} failed: {', '.join(failed)}")
            print("Manifest: CEREBIX_BUILD.md")

        # ---- Rebuild Prompt ----
        try:
            rebuild = input(f"\nRebuild this exact same plan with a different generator model? (y/n): ").strip().lower()
            if rebuild != "y":
                break
            
            print_info("\nSelect a new generator model (or type its ID directly):")
            new_model = choose_model(free_models)
            custom_generator_id = new_model["id"]
        except (EOFError, KeyboardInterrupt):
            break


