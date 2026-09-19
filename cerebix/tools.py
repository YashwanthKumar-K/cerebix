"""
cerebix/tools.py — Tool registry for agent mode.

6 workspace-confined tools that the LLM can invoke via JSON tool calls.
All paths are resolved relative to state.workspace_root (default: cwd).
"""

import os
import subprocess
import glob as glob_module
from pathlib import Path
from . import state
from .config import print_info

# ── Output Limits ────────────────────────────────────────────────────────────

MAX_OUTPUT_BYTES = 8192  # 8 KB cap on tool output to protect context window


# ── Path Safety ──────────────────────────────────────────────────────────────

def _get_workspace() -> Path:
    """Return the current workspace root as a resolved Path."""
    root = state.workspace_root or os.getcwd()
    return Path(root).resolve()


def _safe_path(user_path: str) -> Path:
    """
    Resolve user_path inside the workspace.
    Raises ValueError if the resolved path escapes the workspace root.
    """
    workspace = _get_workspace()
    # Reject absolute paths outright (forces relative paths)
    if os.path.isabs(user_path):
        raise ValueError(f"Absolute paths not allowed: {user_path}")

    resolved = (workspace / user_path).resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        raise ValueError(f"Path escapes workspace: {user_path}")
    return resolved


def _truncate(text: str) -> str:
    """Truncate output to MAX_OUTPUT_BYTES with a notice."""
    if len(text.encode("utf-8", errors="replace")) > MAX_OUTPUT_BYTES:
        truncated = text[:MAX_OUTPUT_BYTES]
        return truncated + "\n…[output truncated to 8KB]…"
    return text


# ── Tool Implementations ─────────────────────────────────────────────────────

def tool_read_file(arguments: dict) -> str:
    """Read file contents. Returns content or ERROR string."""
    try:
        path = _safe_path(arguments["path"])
    except (ValueError, KeyError) as e:
        return f"ERROR: {e}"

    if not path.is_file():
        return f"ERROR: File not found: {arguments['path']}"

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        return _truncate(content)
    except Exception as e:
        return f"ERROR: Could not read file: {e}"


def tool_write_file(arguments: dict) -> str:
    """Create or overwrite a file. Returns OK or ERROR string."""
    try:
        path = _safe_path(arguments["path"])
        content = arguments["content"]
    except (ValueError, KeyError) as e:
        return f"ERROR: {e}"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"OK: wrote {len(content)} chars to {arguments['path']}"
    except Exception as e:
        return f"ERROR: Could not write file: {e}"


def tool_edit_file(arguments: dict) -> str:
    """Replace first occurrence of 'old' with 'new' in a file."""
    try:
        path = _safe_path(arguments["path"])
        old = arguments["old"]
        new = arguments["new"]
    except (ValueError, KeyError) as e:
        return f"ERROR: {e}"

    if not path.is_file():
        return f"ERROR: File not found: {arguments['path']}"

    try:
        text = path.read_text(encoding="utf-8")
        if old not in text:
            return f"ERROR: Old substring not found in {arguments['path']}"
        updated = text.replace(old, new, 1)  # replace first occurrence only
        path.write_text(updated, encoding="utf-8")
        return f"OK: edited {arguments['path']}"
    except Exception as e:
        return f"ERROR: Could not edit file: {e}"


def tool_run_bash(arguments: dict) -> str:
    """Execute a shell command inside the workspace. Gated by state.allow_bash."""
    if not state.allow_bash:
        return "ERROR: Bash tool is disabled. User must run /allow on to enable."

    cmd = arguments.get("cmd", "")
    if not cmd:
        return "ERROR: No command provided."

    timeout = min(arguments.get("timeout", 30), 120)  # cap at 2 minutes
    workspace = _get_workspace()

    try:
        completed = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workspace),
        )
        out = completed.stdout + completed.stderr
        if not out.strip():
            out = f"(exit code {completed.returncode}, no output)"
        return _truncate(out)
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out after {timeout}s"
    except Exception as e:
        return f"ERROR: {e}"


def tool_list_dir(arguments: dict) -> str:
    """List entries in a directory."""
    sub = arguments.get("path", ".")
    try:
        path = _safe_path(sub)
    except ValueError as e:
        return f"ERROR: {e}"

    if not path.is_dir():
        return f"ERROR: Not a directory: {sub}"

    try:
        entries = sorted(path.iterdir())
        lines = []
        for p in entries[:200]:  # cap at 200 entries
            prefix = "[DIR] " if p.is_dir() else "      "
            lines.append(f"{prefix}{p.name}")
        result = "\n".join(lines)
        if len(entries) > 200:
            result += f"\n…[{len(entries) - 200} more entries]…"
        return result or "(empty directory)"
    except Exception as e:
        return f"ERROR: {e}"


def tool_glob(arguments: dict) -> str:
    """Find files matching a glob pattern relative to workspace."""
    pattern = arguments.get("pattern", "")
    if not pattern:
        return "ERROR: No pattern provided."

    workspace = _get_workspace()
    try:
        matches = sorted(
            str(p.relative_to(workspace))
            for p in workspace.glob(pattern)
            if p.is_file()
        )
        if not matches:
            return f"No files matched: {pattern}"
        result = "\n".join(matches[:100])  # cap at 100 results
        if len(matches) > 100:
            result += f"\n…[{len(matches) - 100} more matches]…"
        return result
    except Exception as e:
        return f"ERROR: {e}"


# ── Tool Registry ────────────────────────────────────────────────────────────

TOOL_REGISTRY = {
    "read_file":  tool_read_file,
    "write_file": tool_write_file,
    "edit_file":  tool_edit_file,
    "run_bash":   tool_run_bash,
    "list_dir":   tool_list_dir,
    "glob":       tool_glob,
}

# Human-readable descriptions for system prompt injection
TOOL_DESCRIPTIONS = {
    "read_file":  '{"path": "relative/path.txt"} → file contents',
    "write_file": '{"path": "...", "content": "..."} → creates/overwrites file',
    "edit_file":  '{"path": "...", "old": "...", "new": "..."} → replaces first occurrence',
    "run_bash":   '{"cmd": "...", "timeout": 30} → runs shell command (must be enabled)',
    "list_dir":   '{"path": "."} → lists directory entries',
    "glob":       '{"pattern": "**/*.py"} → finds matching files',
}


def get_available_tools() -> list:
    """Return list of tool names currently available to the model."""
    tools = ["read_file", "write_file", "edit_file", "list_dir", "glob"]
    if state.allow_bash:
        tools.append("run_bash")
    return tools


def get_tool_prompt_section() -> str:
    """Generate tool-usage instructions for the system prompt."""
    available = get_available_tools()
    if not available:
        return ""

    workspace = _get_workspace()
    lines = [
        f"\nYou have access to tools. Workspace: {workspace}",
        "Available tools:",
    ]
    for name in available:
        desc = TOOL_DESCRIPTIONS.get(name, "")
        lines.append(f"  - {name}: {desc}")

    lines.extend([
        "",
        'To use a tool, output ONLY a JSON object: {"tool": "<name>", "arguments": {...}}',
        "No extra text before or after the JSON. After the tool runs, you will see the result and can continue.",
    ])
    return "\n".join(lines)
