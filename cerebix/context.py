import os
import fnmatch
from . import state
from .config import IGNORE_DIRS, IGNORE_EXTENSIONS, MAX_FILE_SIZE_KB, CHARS_PER_TOKEN, print_info, print_error, print_warn
from .models import format_ctx

_EXT_LANG_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".json": "json",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".ps1": "powershell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sql": "sql",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".toml": "toml",
    ".xml": "xml",
}


def _get_lang_for_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    return _EXT_LANG_MAP.get(ext, "")


def _generate_ascii_tree(file_paths):
    """Generate a clean ASCII file tree representation from a list of relative paths."""
    tree = {}
    for path in sorted(file_paths):
        parts = path.replace("\\", "/").split("/")
        curr = tree
        for p in parts:
            curr = curr.setdefault(p, {})

    lines = []
    def _walk(d, prefix=""):
        items = list(d.items())
        for idx, (name, subtree) in enumerate(items):
            is_last = idx == len(items) - 1
            connector = "└── " if is_last else "├── "
            if subtree:  # directory
                lines.append(f"{prefix}{connector}{name}/")
                extension = "    " if is_last else "│   "
                _walk(subtree, prefix + extension)
            else:
                lines.append(f"{prefix}{connector}{name}")
    _walk(tree)
    return "\n".join(lines)


def _file_sort_key(rel_path):
    """Sort files logically: scaffolding & models first, main entrypoints last."""
    p = rel_path.lower().replace("\\", "/")
    base = os.path.basename(p)
    if base in ("readme.md", "requirements.txt", "package.json", "pyproject.toml", ".env.example", "setup.py"):
        return (0, p)
    if "config" in base or "schema" in base or "model" in base or "state" in base:
        return (1, p)
    if "util" in p or "helper" in p or "common" in p:
        return (2, p)
    if base in ("main.py", "index.js", "app.py", "server.js"):
        return (4, p)
    return (3, p)


import difflib

_BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".tar",
    ".gz", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".bin", ".iso",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".pyc", ".class", ".db", ".sqlite"
}


def load_file_as_prompt(filepath, instruction="Review this file:"):
    if os.path.isdir(filepath):
        return "ERROR: That's a folder, not a file. Use /project instead."

    ext = os.path.splitext(filepath)[1].lower()
    if ext in _BINARY_EXTENSIONS:
        return f"ERROR: '{os.path.basename(filepath)}' is a binary file ({ext}). Cerebix reviews text, source code, and markdown documents."

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        parent = os.path.dirname(filepath) or "."
        target_name = os.path.basename(filepath)
        suggestion = ""
        try:
            candidates = os.listdir(parent)
            matches = difflib.get_close_matches(target_name, candidates, n=1, cutoff=0.5)
            if matches:
                suggested_path = os.path.join(parent, matches[0])
                suggestion = f" Did you mean: '{suggested_path}'?"
        except Exception:
            pass
        return f"ERROR: File not found: '{filepath}'.{suggestion}"
    except UnicodeDecodeError:
        return f"ERROR: '{os.path.basename(filepath)}' contains binary data — cannot read as UTF-8 text."
    except PermissionError:
        return f"ERROR: Permission denied — cannot read '{filepath}'."

    lang = _get_lang_for_file(filepath)
    lines = content.splitlines()
    line_count = len(lines)
    size_kb = os.path.getsize(filepath) / 1024

    # Truncation guard for massive individual files (>1500 lines) to prevent blowing context
    if line_count > 1500:
        content = "\n".join(lines[:1500]) + f"\n\n[File truncated at 1500 lines due to context limits. Full file ({line_count} lines) exists on disk.]"

    return f"{instruction}\n\nFile: {os.path.basename(filepath)} ({line_count} lines, {size_kb:.1f} KB)\n```{lang}\n{content}\n```"


def load_project_as_prompt(folder_path, instruction="Review this project:"):
    if not os.path.isdir(folder_path):
        return None

    file_entries = []

    # Patterns and directories we MUST NEVER upload to an external API
    SECRET_PATTERNS = [
        ".env", ".env.*", "*.env", "*.pem", "*.key", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
        "credentials.json", ".npmrc", ".pypirc",
        "*.p12", "*.pfx", "*.cer", "*.crt", "*.keystore", "*.jks", "*.jceks",
        "secrets.yaml", "secrets.yml",
        "*.tfstate", "*.tfstate.*", "*.tfvars",
        "kubeconfig", "*.kubeconfig",
        "*.secret", "*.private",
    ]
    SECRET_DIRS = {".ssh", ".aws", ".azure", ".kube", ".docker"}

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and d not in SECRET_DIRS]
        for fname in files:
            # Check secret patterns
            is_secret = any(fnmatch.fnmatch(fname.lower(), pat) for pat in SECRET_PATTERNS)
            if is_secret:
                continue

            ext = os.path.splitext(fname)[1].lower()
            if ext in IGNORE_EXTENSIONS:
                continue
            fpath = os.path.join(root, fname)
            try:
                if os.path.getsize(fpath) > MAX_FILE_SIZE_KB * 1024:
                    continue
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, PermissionError):
                continue
            rel = os.path.relpath(fpath, folder_path)
            file_entries.append((rel, content))

    if not file_entries:
        return "ERROR: No readable text files found in that folder."

    # Sort files logically: scaffolding/configs/utils first, entry points last
    file_entries.sort(key=lambda x: _file_sort_key(x[0]))
    rel_paths = [e[0] for e in file_entries]

    # Generate visual file structure tree
    ascii_tree = _generate_ascii_tree(rel_paths)
    combined = [
        f"{instruction}\n\nProject: {os.path.basename(folder_path)}",
        f"Project Structure:\n```text\n{ascii_tree}\n```\n",
    ]

    for rel, content in file_entries:
        lang = _get_lang_for_file(rel)
        line_count = len(content.splitlines())
        combined.append(f"--- File: {rel} ({line_count} lines) ---\n```{lang}\n{content}\n```\n")

    result = "\n".join(combined)
    est_tokens = len(result) // CHARS_PER_TOKEN
    file_count = len(file_entries)
    ctx_limit = state.current_model.get("context", 0) if state.current_model else 0
    model_name = state.current_model.get("name", "current model") if state.current_model else "current model"
    print_info(f"Collected {file_count} files — ~{est_tokens:,} tokens")

    if isinstance(ctx_limit, int) and ctx_limit > 0 and est_tokens > ctx_limit * 0.8:
        print_error(
            f"⚠ Project is ~{est_tokens:,} tokens but {model_name} only supports {format_ctx(ctx_limit)}. "
            "The model will likely return an empty or broken response!"
        )
        print_info("Tip: Use /select to pick a model with a larger context window, then retry.")
        if input("Send anyway? (y/n): ").strip().lower() != "y":
            return "ERROR: Cancelled."
    elif est_tokens > 30000:
        print_warn(
            f"⚠ Large prompt (~{est_tokens:,} tokens). Some free models may struggle with this. "
            "If you get an empty response, try /select and pick a model with a bigger context window."
        )

    return result


