import os
import fnmatch
from . import state
from .config import IGNORE_DIRS, IGNORE_EXTENSIONS, MAX_FILE_SIZE_KB, CHARS_PER_TOKEN, print_info, print_error
from .models import format_ctx

def load_file_as_prompt(filepath, instruction="Review this file:"):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return None
    except UnicodeDecodeError:
        return "ERROR: Binary file — can't read as text."
    return f"{instruction}\n\nFile: {os.path.basename(filepath)}\n```\n{content}\n```"


# Add secret filtering right inside load_project_as_prompt
import fnmatch

def load_project_as_prompt(folder_path, instruction="Review this project:"):
    if not os.path.isdir(folder_path):
        return None

    combined = [f"{instruction}\n\nProject: {os.path.basename(folder_path)}\n"]
    file_count = 0

    # Patterns we MUST NEVER upload to OpenRouter
    SECRET_PATTERNS = [".env", ".env.*", "*.pem", "*.key", "id_rsa", "credentials.json", ".npmrc", ".pypirc"]

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for fname in files:
            # Check secret patterns
            is_secret = any(fnmatch.fnmatch(fname, pat) for pat in SECRET_PATTERNS)
            if is_secret:
                continue

            ext = os.path.splitext(fname)[1].lower()
            if ext in IGNORE_EXTENSIONS:
                continue
            fpath = os.path.join(root, fname)
            try:
                if os.path.getsize(fpath) > MAX_FILE_SIZE_KB * 1024:
                    combined.append(f"\n[SKIPPED - too large]: {fpath}\n")
                    continue
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, PermissionError):
                continue
            rel = os.path.relpath(fpath, folder_path)
            combined.append(f"\n--- File: {rel} ---\n```\n{content}\n```\n")
            file_count += 1

    if file_count == 0:
        return "ERROR: No readable text files found in that folder."

    result = "\n".join(combined)
    est_tokens = len(result) // CHARS_PER_TOKEN
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


