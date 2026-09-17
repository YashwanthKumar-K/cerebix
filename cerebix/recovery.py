"""Cerebix Error Classification & Alternative Recovery Flows.

Provides structured diagnosis and individual recovery flows for:
- SSL certificate verification errors (captive portals, proxies, VPNs)
- Internet / DNS offline failures
- Network timeouts (>60s)
- HTTP 429 rate limit exceeded
- HTTP 400 context window overflow
- HTTP 500/502/503 provider outages
- HTTP 401 unauthorized / invalid API key
- Empty model responses
"""

import os
import re
import sys
import time
import webbrowser
from enum import Enum
from pathlib import Path

from . import state
from .config import (
    HAS_RICH,
    console,
    print_info,
    print_warn,
    print_error,
    print_success,
    get_ssl_verify,
    set_ssl_verify,
    load_user_config,
    save_user_config,
)
from .routing import classify_prompt

if HAS_RICH:
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich import box


class ErrorType(Enum):
    SSL_ERROR = "ssl_error"
    OFFLINE = "offline"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    CONTEXT_EXCEEDED = "context_exceeded"
    PROVIDER_OUTAGE = "provider_outage"
    UNAUTHORIZED = "unauthorized"
    EMPTY_RESPONSE = "empty_response"
    GENERIC = "generic"


class Action(Enum):
    RETRY_SAME = "retry_same"
    SWITCH_MODEL = "switch_model"
    BYPASS_SSL = "bypass_ssl"
    SAVE_DRAFT = "save_draft"
    UPDATE_KEY = "update_key"
    ABORT = "abort"


def is_ssl_error(exc):
    """Detect if an exception is an SSL certificate verification failure."""
    msg = str(exc).lower()
    return (
        "certificate_verify_failed" in msg
        or "self-signed certificate" in msg
        or "sslerror" in msg
        or "sslcertverificationerror" in msg
    )


def is_offline_error(exc):
    """Detect if an exception is due to no internet, DNS resolution, or network drop."""
    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "name resolution",
            "getaddrinfo failed",
            "connection refused",
            "network is unreachable",
            "failed to establish a new connection",
            "connection reset",
            "connection aborted",
        )
    )


def is_timeout_error(exc):
    """Detect if request timed out."""
    msg = str(exc).lower()
    return "timed out" in msg or "timeout" in msg


def classify_error(exc=None, status_code=None, error_msg=None):
    """Classify an HTTP response code or Python exception into an ErrorType."""
    if status_code == 401:
        return ErrorType.UNAUTHORIZED
    if status_code == 429:
        return ErrorType.RATE_LIMIT
    if status_code in (500, 502, 503, 504):
        return ErrorType.PROVIDER_OUTAGE

    combined = (str(exc or "") + " " + str(error_msg or "")).lower()

    if "context_length_exceeded" in combined or "maximum context length" in combined or "context window" in combined:
        return ErrorType.CONTEXT_EXCEEDED
    if is_ssl_error(combined):
        return ErrorType.SSL_ERROR
    if is_offline_error(combined):
        return ErrorType.OFFLINE
    if is_timeout_error(combined):
        return ErrorType.TIMEOUT
    if status_code == 400:
        if any(w in combined for w in ("token", "context", "length", "too large")):
            return ErrorType.CONTEXT_EXCEEDED

    return ErrorType.GENERIC


def show_error_panel(title, summary, causes=None, solutions=None):
    """Render a structured, beautiful diagnostic panel."""
    lines = [f"[bold red]{summary}[/]\n"]
    if causes:
        lines.append("[bold yellow]Why this happens:[/]")
        for c in causes:
            lines.append(f" • {c}")
        lines.append("")
    if solutions:
        lines.append("[bold green]Solutions:[/]")
        for i, s in enumerate(solutions, 1):
            lines.append(f" {i}. {s}")

    content = "\n".join(lines)

    if HAS_RICH:
        console.print()
        console.print(Panel(content, title=f"[bold red]{title}[/]", border_style="red", box=box.ROUNDED))
    else:
        print("\n" + "=" * 65)
        print(f"{title}: {summary}")
        if causes:
            print("Why this happens:")
            for c in causes:
                print(f"  - {c}")
        if solutions:
            print("Solutions:")
            for s in solutions:
                print(f"  - {s}")
        print("=" * 65)


def get_fallback_model(current_model, free_models, prompt="", exclude_ids=None):
    """Select the best alternative free model, avoiding failing models."""
    if not free_models:
        return None

    exclude = set(exclude_ids or [])
    if current_model and "id" in current_model:
        exclude.add(current_model["id"])
    exclude.update(state.failed_models)

    candidates = [m for m in free_models if m.get("id") not in exclude]
    if not candidates:
        # If all were excluded, allow candidates outside the immediate failing one
        candidates = [m for m in free_models if current_model and m.get("id") != current_model.get("id")]
    if not candidates:
        return None

    # Priority 1: Match category heuristic
    if prompt:
        category = classify_prompt(prompt)
        from .routing import _heuristic_pick
        pick = _heuristic_pick(category, candidates)
        if pick:
            return pick

    # Priority 2: Highest context window candidate
    return max(candidates, key=lambda m: m.get("context", 0) or 0)


def get_high_context_model(current_model, free_models):
    """Find a free model with a large context window (>64k or maximum available)."""
    if not free_models:
        return None
    curr_id = (current_model or {}).get("id")
    candidates = [m for m in free_models if m.get("id") != curr_id]
    if not candidates:
        candidates = free_models
    return max(candidates, key=lambda m: m.get("context", 0) or 0)


def handle_error_flow(error_type, exc=None, status_code=None, current_model=None, free_models=None, prompt="", wait_seconds=5):
    """Execute the individual alternative recovery flow for the classified error.

    Returns:
        (Action, payload)
        where payload may be a new model dict, new api key, or None.
    """
    free_models = free_models or []
    mname = (current_model or {}).get("name", "active model")

    # =========================================================================
    # Flow 1: SSL Certificate Verification Error
    # =========================================================================
    if error_type == ErrorType.SSL_ERROR:
        show_error_panel(
            title="🔒 SSL Certificate Verification Failed",
            summary="Cerebix could not verify the secure HTTPS certificate for openrouter.ai.",
            causes=[
                "Campus, office, or hotel Wi-Fi requiring a captive portal login in your browser",
                "Corporate VPN or network proxy intercepting HTTPS traffic (Zscaler, Cisco, Fortinet)",
                "Antivirus software inspecting SSL connections (Kaspersky, Avast, Bitdefender)",
            ],
            solutions=[
                "Open your browser and complete any pending Wi-Fi login",
                "Disable active VPN or antivirus HTTPS scanning",
                "Bypass SSL verification for this session (run /ssl or answer below)",
            ],
        )
        try:
            choice = input("\nBypass SSL verification for this session? (y/n) [default: y]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return Action.ABORT, None

        if choice in ("", "y", "yes"):
            set_ssl_verify(False, persist=False)
            print_success("SSL verification disabled for this session.")
            print_info("Tip: Use /ssl anytime to toggle strict SSL verification.")
            return Action.BYPASS_SSL, None
        return Action.ABORT, None

    # =========================================================================
    # Flow 2: Network Offline / DNS Failure
    # =========================================================================
    elif error_type == ErrorType.OFFLINE:
        show_error_panel(
            title="🌐 Network Connection Offline",
            summary="Cerebix cannot connect to openrouter.ai.",
            causes=[
                "Wi-Fi or Ethernet disconnected",
                "Airplane mode or active network change",
                "DNS server resolution failure",
            ],
            solutions=[
                "Check your internet connection",
                "Verify https://openrouter.ai loads in your browser",
                "Save your prompt as a draft so nothing is lost",
            ],
        )
        try:
            choice = input("\nOptions: [R]etry connection | [S]ave prompt draft | [C]ancel [r/s/c]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return Action.ABORT, None

        if choice in ("r", "retry"):
            return Action.RETRY_SAME, None
        elif choice in ("s", "save"):
            state.draft_prompt = prompt
            print_success("Prompt saved to draft! It will be restored as soon as you reconnect.")
            return Action.SAVE_DRAFT, prompt
        return Action.ABORT, None

    # =========================================================================
    # Flow 3: Request Timeout (>60s)
    # =========================================================================
    elif error_type == ErrorType.TIMEOUT:
        show_error_panel(
            title="⏱ Request Timed Out",
            summary=f"The model provider for {mname} did not respond within 60 seconds.",
            causes=[
                "The upstream model backend is experiencing heavy load",
                "Network latency or packet loss",
            ],
            solutions=[
                "Retry with the same model",
                "Automatically switch to an alternative fast free model",
            ],
        )
        fallback = get_fallback_model(current_model, free_models, prompt)
        fb_hint = f" ({fallback['name']})" if fallback else ""
        try:
            choice = input(f"\nOptions: [1] Retry same model | [2] Switch to alternative model{fb_hint} | [3] Cancel [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return Action.ABORT, None

        if choice == "2" and fallback:
            state.failed_models.add((current_model or {}).get("id"))
            print_success(f"Switching to alternative model: {fallback['name']}")
            return Action.SWITCH_MODEL, fallback
        elif choice == "1":
            return Action.RETRY_SAME, None
        return Action.ABORT, None

    # =========================================================================
    # Flow 4: Rate Limit (HTTP 429)
    # =========================================================================
    elif error_type == ErrorType.RATE_LIMIT:
        mid = (current_model or {}).get("id")
        if mid:
            state.failed_models.add(mid)
        fallback = get_fallback_model(current_model, free_models, prompt)
        fb_hint = f" [Press 's' to switch to {fallback['name']}]" if fallback else ""

        print_warn(f"⏳ Rate limit reached on {mname}. OpenRouter free tier is throttled.")
        if fallback:
            print_info(f"   Alternative model available: [cyan]{fallback['name']}[/]")

        try:
            prompt_str = f"Options: [W]ait {wait_seconds:.0f}s and retry | [S]witch model immediately | [C]ancel [w/s/c]: "
            choice = input(prompt_str).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return Action.ABORT, None

        if choice in ("s", "switch") and fallback:
            print_success(f"Switching to {fallback['name']}...")
            return Action.SWITCH_MODEL, fallback
        elif choice in ("", "w", "wait"):
            time.sleep(wait_seconds)
            return Action.RETRY_SAME, None
        return Action.ABORT, None

    # =========================================================================
    # Flow 5: Context Window Exceeded (HTTP 400)
    # =========================================================================
    elif error_type == ErrorType.CONTEXT_EXCEEDED:
        hi_model = get_high_context_model(current_model, free_models)
        hi_hint = f" (Switch to {hi_model['name']} - {hi_model.get('context', 0)//1000}k ctx)" if hi_model else ""

        show_error_panel(
            title="📏 Context Window Limit Exceeded",
            summary=f"The prompt or file sent exceeds {mname}'s maximum context window.",
            causes=[
                "The file or project ingested via /file or /project is too large",
                "Conversation history has accumulated too many tokens",
            ],
            solutions=[
                f"Switch to a high-context free model{hi_hint}",
                "Clear conversation history with /clear and resend the file",
            ],
        )
        try:
            choice = input(f"\nOptions: [1] Auto-switch to high-context model | [2] Clear history & retry | [3] Cancel [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return Action.ABORT, None

        if choice in ("", "1") and hi_model:
            print_success(f"Switching to high-context model: {hi_model['name']}")
            return Action.SWITCH_MODEL, hi_model
        elif choice == "2":
            state.conversation.clear()
            print_success("Conversation history cleared. Retrying...")
            return Action.RETRY_SAME, None
        return Action.ABORT, None

    # =========================================================================
    # Flow 6: Upstream Provider Outage (HTTP 500 / 502 / 503 / 504)
    # =========================================================================
    elif error_type == ErrorType.PROVIDER_OUTAGE:
        mid = (current_model or {}).get("id")
        if mid:
            state.failed_models.add(mid)
        fallback = get_fallback_model(current_model, free_models, prompt)

        show_error_panel(
            title=f"☁ Upstream Provider Outage ({status_code or 'HTTP 50x'})",
            summary=f"The backend provider hosting {mname} is currently down or failing.",
            causes=[
                "Provider maintenance, GPU capacity exhaustion, or API gateway failure",
                "This is on the model host's side, not your connection",
            ],
            solutions=[
                f"Switch to an alternative free model from another provider ({fallback['name'] if fallback else 'another model'})",
                "Try again later with this model",
            ],
        )
        if fallback:
            try:
                choice = input(f"\nSwitch to {fallback['name']} and retry now? (y/n) [default: y]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return Action.ABORT, None
            if choice in ("", "y", "yes"):
                print_success(f"Switched to {fallback['name']}.")
                return Action.SWITCH_MODEL, fallback
        return Action.ABORT, None

    # =========================================================================
    # Flow 7: Invalid or Missing API Key (HTTP 401)
    # =========================================================================
    elif error_type == ErrorType.UNAUTHORIZED:
        show_error_panel(
            title="🔑 Invalid or Expired API Key",
            summary="OpenRouter rejected the request as unauthorized.",
            causes=[
                "The configured OpenRouter API key has been revoked, expired, or mistyped",
            ],
            solutions=[
                "Enter a valid API key below",
                "Press Enter to open https://openrouter.ai/keys in your browser",
            ],
        )
        try:
            new_key = input("\nEnter new OpenRouter API Key (or press Enter to open browser): ").strip()
        except (EOFError, KeyboardInterrupt):
            return Action.ABORT, None

        if not new_key:
            webbrowser.open("https://openrouter.ai/keys")
            try:
                new_key = input("Paste your API key here: ").strip()
            except (EOFError, KeyboardInterrupt):
                return Action.ABORT, None

        if new_key.startswith("sk-or-"):
            cfg = load_user_config()
            cfg["openrouter_api_key"] = new_key
            save_user_config(cfg)
            os.environ["OPENROUTER_API_KEY"] = new_key
            print_success("API key updated and saved! Retrying request...")
            return Action.UPDATE_KEY, new_key
        else:
            print_error("Invalid key format (expected key starting with 'sk-or-').")
            return Action.ABORT, None

    # =========================================================================
    # Flow 8: Empty Response
    # =========================================================================
    elif error_type == ErrorType.EMPTY_RESPONSE:
        fallback = get_fallback_model(current_model, free_models, prompt)
        show_error_panel(
            title="⚠ Empty Response Returned",
            summary=f"{mname} returned 0 output tokens.",
            causes=[
                "Content moderation / safety filter blocked generation",
                "Model is overloaded or dropped the stream prematurely",
                "Prompt was too large for context allocation",
            ],
            solutions=[
                f"Retry with alternative model ({fallback['name'] if fallback else 'another model'})",
                "Retry with the same model",
            ],
        )
        try:
            choice = input("\nOptions: [1] Switch model | [2] Retry same | [3] Cancel [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return Action.ABORT, None

        if choice in ("", "1") and fallback:
            print_success(f"Switching to {fallback['name']}...")
            return Action.SWITCH_MODEL, fallback
        elif choice == "2":
            return Action.RETRY_SAME, None
        return Action.ABORT, None

    # =========================================================================
    # Generic Fallback
    # =========================================================================
    clean_msg = str(exc or "Unknown network error")
    if "Max retries exceeded with url" in clean_msg:
        m = re.search(r"Caused by ([^)]+\))", clean_msg)
        if m:
            clean_msg = m.group(1)
    print_error(f"Request failed: {clean_msg}")
    return Action.ABORT, None
