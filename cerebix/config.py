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

console = Console() if HAS_RICH else None


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


# ---------- API Key ----------

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "X-Title": "Cerebix",
}

import webbrowser

def check_api_key():
    if not API_KEY:
        print_error("OPENROUTER_API_KEY environment variable not set!")
        print_info("You need a free OpenRouter API key to use Cerebix.")
        print_info("Opening browser to: https://openrouter.ai/settings/keys")
        
        try:
            webbrowser.open("https://openrouter.ai/settings/keys")
        except Exception:
            pass
            
        print_info("\nSet it with:")
        if sys.platform == "win32":
            print_info("  set OPENROUTER_API_KEY=sk-or-v1-...")
            print_info("  (or permanently via System > Environment Variables)")
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

