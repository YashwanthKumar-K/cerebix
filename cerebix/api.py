import requests
import time
import json
from .config import print_error, print_warn, get_headers, HAS_RICH, console, Fore, Style
from .spinner import ThinkingSpinner, _CHAT_MESSAGES
if HAS_RICH:
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich import box


def _get_retry_wait(resp, default_seconds):
    """Extract Retry-After header if present, capped at 60s."""
    retry_header = resp.headers.get("Retry-After")
    if retry_header:
        try:
            val = float(retry_header)
            return min(max(val, 1.0), 60.0)
        except (ValueError, TypeError):
            pass
    return default_seconds


def stream_response(payload):
    """POST with stream=True, print tokens live, return full text."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload["stream"] = True

    backoff = [5, 15, 30]
    spinner = ThinkingSpinner(_CHAT_MESSAGES)
    spinner.start()
    resp = None

    for attempt in range(len(backoff) + 1):
        try:
            resp = requests.post(url, headers=get_headers(), json=payload, stream=True, timeout=60)
            if resp.status_code == 429:
                spinner.stop()
                if attempt < len(backoff):
                    wait_time = _get_retry_wait(resp, backoff[attempt])
                    print_warn(f"Rate limited. Retrying in {wait_time:.0f}s...")
                    time.sleep(wait_time)
                    spinner.start()
                    continue
                print_error("Rate limited after multiple attempts.")
                return None
            if resp.status_code != 200:
                spinner.stop()
                try:
                    msg = resp.json().get("error", {}).get("message", resp.text[:200])
                except Exception:
                    msg = resp.text[:200]
                print_error(f"API Error ({resp.status_code}): {msg}")
                return None
            break
        except requests.RequestException as e:
            spinner.stop()
            if attempt < len(backoff):
                print_warn(f"Request failed: {e}. Retrying in {backoff[attempt]}s...")
                time.sleep(backoff[attempt])
                spinner.start()
                continue
            print_error(f"Request failed: {e}")
            return None

    full_text = ""
    start_time = time.time()
    header_printed = False

    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                payload_str = line[6:]
                if payload_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload_str)
                    choices = chunk.get("choices", [])
                    if choices and len(choices) > 0:
                        token = choices[0].get("delta", {}).get("content", "")
                        if token:
                            if not header_printed:
                                spinner.stop()
                                if HAS_RICH:
                                    console.print("[bold green]Assistant:[/]")
                                else:
                                    print(f"{Fore.GREEN}Assistant:{Style.RESET_ALL}")
                                header_printed = True
                            print(token, end="", flush=True)
                            full_text += token
                except json.JSONDecodeError:
                    continue
    finally:
        spinner.stop()

    elapsed = time.time() - start_time
    print()  # newline

    # Detect empty responses
    if not full_text.strip():
        print_warn(
            f"⚠ Model returned an empty response after {elapsed:.1f}s. "
            "This usually means the prompt was too large for the model's context window, "
            "or the model is overloaded. Try /select to switch to a different model."
        )
        return None

    # Re-render as formatted markdown panel
    if HAS_RICH:
        console.print()
        console.print(Panel(
            Markdown(full_text),
            title=f"[bold green]Response[/] [dim]({elapsed:.1f}s)[/]",
            border_style="green",
            box=box.ROUNDED,
        ))
    else:
        print(f"\n[Generated in {elapsed:.1f}s]")

    return full_text


def ask_model_isolated(prompt, model_id, max_retries=3):
    """Send a single prompt (no state.conversation history). Used for fan-out & consensus."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {"model": model_id, "messages": [{"role": "user", "content": prompt}]}

    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=get_headers(), json=payload, timeout=60)
            if resp.status_code == 429:
                if attempt < max_retries - 1:
                    wait = _get_retry_wait(resp, 5 * (2 ** attempt))
                    print_warn(f"Rate limited. Waiting {wait:.0f}s...")
                    time.sleep(wait)
                    continue
                return f"Error: Rate limited after {max_retries} attempts."
            if resp.status_code != 200:
                try:
                    return f"API Error: {resp.json().get('error', {}).get('message', resp.text[:200])}"
                except Exception:
                    return f"HTTP {resp.status_code}: {resp.text[:200]}"
            data = resp.json()
            if "error" in data:
                return f"API Error: {data['error'].get('message', data['error'])}"
            choices = data.get("choices", [])
            if choices and len(choices) > 0:
                return choices[0].get("message", {}).get("content", "")
            return ""
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                wait = 5 * (2 ** attempt)
                print_warn(f"Request error: {e}. Retrying in {wait}s...")
                time.sleep(wait)
                continue
            return f"Error: {e}"
    return "Error: Failed after all retries."


