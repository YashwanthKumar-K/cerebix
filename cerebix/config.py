#!/usr/bin/env python3
"""Cerebix — Multi-Model AI Orchestration CLI.

A single-file CLI powered by OpenRouter's free models.
Features: streaming, smart auto-routing, consensus/jury mode, fan-out,
          scorecard, system prompts, file/project context, and more.
"""

import os
import json
import requests
import shlex
import time
import re
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------- Rich library ----------
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
    HAS_RICH = True
    class Fore: RED = GREEN = YELLOW = CYAN = MAGENTA = BLUE = WHITE = ""
    class Style: RESET_ALL = BRIGHT = ""
except ImportError:
    HAS_RICH = False
    class Fore: RED = GREEN = YELLOW = CYAN = MAGENTA = BLUE = WHITE = ""
    class Style: RESET_ALL = BRIGHT = ""

if not HAS_RICH:
    try:
        from colorama import init, Fore, Style
        init(autoreset=True)
    except ImportError:
        class Fore:
            RED = GREEN = YELLOW = CYAN = MAGENTA = BLUE = WHITE = ""
        class Style:
            RESET_ALL = BRIGHT = ""

console = Console(force_terminal=True) if HAS_RICH else None


# ---------- Print helpers ----------

def print_error(text):
    if HAS_RICH:
        console.print(f"[bold red][x] {text}[/]")
    else:
        print(f"{Fore.RED}[x] {text}{Style.RESET_ALL}")

def print_success(text):
    if HAS_RICH:
        console.print(f"[bold green][v] {text}[/]")
    else:
        print(f"{Fore.GREEN}[v] {text}{Style.RESET_ALL}")

def print_info(text):
    if HAS_RICH:
        console.print(f"[bold cyan]{text}[/]")
    else:
        print(f"{Fore.CYAN}{text}{Style.RESET_ALL}")

def print_warn(text):
    if HAS_RICH:
        console.print(f"[bold yellow]{text}[/]")
    else:
        print(f"{Fore.YELLOW}{text}{Style.RESET_ALL}")


from pathlib import Path
import webbrowser

# ---------- Local User Configuration ----------

CEREBIX_DIR = Path.home() / ".cerebix"
CONFIG_FILE = CEREBIX_DIR / "config.json"


def load_user_config():
    """Load user preferences and credentials from ~/.cerebix/config.json."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_user_config(cfg):
    """Save user preferences and credentials to ~/.cerebix/config.json."""
    try:
        CEREBIX_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print_warn(f"Could not save config file: {e}")


def get_ssl_verify():
    """Check whether SSL verification is enabled from state, env, or config."""
    from . import state
    if hasattr(state, "ssl_verify") and state.ssl_verify is not None:
        return state.ssl_verify
    # Env var overrides
    if os.environ.get("CEREBIX_INSECURE_SSL", "").lower() in ("1", "true", "yes") or \
       os.environ.get("CEREBIX_NO_SSL_VERIFY", "").lower() in ("1", "true", "yes"):
        state.ssl_verify = False
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        return False
    cfg = load_user_config()
    val = cfg.get("ssl_verify", True)
    state.ssl_verify = val
    if not val:
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
    return val


def set_ssl_verify(verify: bool, persist: bool = False):
    """Set SSL verification state and optionally persist to config."""
    from . import state
    state.ssl_verify = verify
    if not verify:
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
    if persist:
        cfg = load_user_config()
        cfg["ssl_verify"] = verify
        save_user_config(cfg)


def get_render_mode():
    """Get active render mode: 'panel' (default) or 'stream'."""
    from . import state
    if hasattr(state, "render_mode") and state.render_mode:
        return state.render_mode
    cfg = load_user_config()
    val = cfg.get("render_mode", "panel")
    state.render_mode = val
    return val


def set_render_mode(mode: str, persist: bool = False):
    """Set active render mode ('panel' or 'stream') and optionally persist to config."""
    from . import state
    mode = "stream" if mode == "stream" else "panel"
    state.render_mode = mode
    if persist:
        cfg = load_user_config()
        cfg["render_mode"] = mode
        save_user_config(cfg)




def get_api_key():
    """Get API key from environment variable or ~/.cerebix/config.json."""
    # 1. Environment variable takes precedence
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    # 2. Local config file fallback
    cfg = load_user_config()
    return cfg.get("openrouter_api_key", "").strip()


def get_headers():
    """Dynamically build request headers with the active API key."""
    key = get_api_key()
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Title": "Cerebix",
    }


class _DynamicHeaders(dict):
    """Backwards-compatible dict wrapper that dynamically delegates to get_headers()."""
    def __getitem__(self, key):
        return get_headers()[key]
    def get(self, key, default=None):
        return get_headers().get(key, default)
    def copy(self):
        return get_headers()
    def __iter__(self):
        return iter(get_headers())
    def __len__(self):
        return len(get_headers())
    def __repr__(self):
        return repr(get_headers())


HEADERS = _DynamicHeaders()


def check_api_key():
    """Verify that an API key is available. If missing, open browser and offer interactive prompt."""
    key = get_api_key()
    if key:
        return key

    print_error("OpenRouter API key not found!")
    print_info("You need a free OpenRouter API key to use Cerebix.")
    print_info("Opening browser to: https://openrouter.ai/settings/keys")

    try:
        webbrowser.open("https://openrouter.ai/settings/keys")
    except Exception:
        pass

    print_info("\nPaste your OpenRouter API key below to save it permanently.")
    try:
        entered_key = input("API Key (or press Enter to exit): ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(1)

    if entered_key:
        cfg = load_user_config()
        cfg["openrouter_api_key"] = entered_key
        save_user_config(cfg)
        print_success(f"API key saved to {CONFIG_FILE}!")
        return entered_key

    print_warn("\nNo API key provided. Set it manually:")
    if sys.platform == "win32":
        print_info("  setx OPENROUTER_API_KEY \"sk-or-v1-...\"")
    else:
        print_info('  export OPENROUTER_API_KEY="sk-or-v1-..."')
    sys.exit(1)

# ---------- Constants ----------

HISTORY_FILE    = "chat_history.json"
SCORECARD_FILE  = "scorecard.json"
CHARS_PER_TOKEN = 4
MAX_FILE_SIZE_KB = 200
IGNORE_DIRS      = {".git", "__pycache__", "node_modules", "venv", ".venv", "dist", "build", ".next", ".cache"}
IGNORE_EXTENSIONS = {".pyc", ".exe", ".dll", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz", ".so", ".o", ".class"}

