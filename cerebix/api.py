import requests
import time
import json
from .config import (
    print_error,
    print_warn,
    print_success,
    print_info,
    get_headers,
    get_ssl_verify,
    HAS_RICH,
    console,
    Fore,
    Style,
)
from .spinner import ThinkingSpinner, _CHAT_MESSAGES
from .recovery import classify_error, handle_error_flow, ErrorType, Action
from . import state

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


def clean_mojibake(text):
    """Sanitize common UTF-8 mojibake artifacts from mismatched terminal decoders."""
    if not text or "â" not in text:
        return text
    replacements = [
        ("â€”", "—"),
        ("â€“", "–"),
        ("â€™", "'"),
        ("â€˜", "'"),
        ("â€œ", '"'),
        ("â€\x9d", '"'),
        ("â€¢", "•"),
        ("â€¦", "…"),
        (" â ", " — "),
        ("â", "—"),
    ]
    for bad, good in replacements:
        text = text.replace(bad, good)
    return text


def stream_response(payload, free_models=None):
    """POST with stream=True, print tokens live, return full text with automated recovery."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload["stream"] = True

    # Extract user prompt for recovery context
    user_msgs = [m.get("content", "") for m in payload.get("messages", []) if m.get("role") == "user"]
    prompt = user_msgs[-1] if user_msgs else ""
    current_model = state.current_model or {"id": payload.get("model", ""), "name": payload.get("model", "")}

    backoff = [5, 15, 30]
    spinner = ThinkingSpinner(_CHAT_MESSAGES)
    spinner.start()
    resp = None

    for attempt in range(len(backoff) + 1):
        try:
            resp = requests.post(
                url,
                headers=get_headers(),
                json=payload,
                stream=True,
                timeout=60,
                verify=get_ssl_verify(),
            )
            if resp.status_code == 200:
                break

            # Handle HTTP Errors via Recovery Engine
            spinner.stop()
            error_data = {}
            try:
                error_data = resp.json().get("error", {})
                error_msg = error_data.get("message", resp.text[:200]) if isinstance(error_data, dict) else str(error_data)
            except Exception:
                error_msg = resp.text[:200]

            err_type = classify_error(status_code=resp.status_code, error_msg=error_msg)
            wait_s = _get_retry_wait(resp, backoff[min(attempt, len(backoff) - 1)])
            action, val = handle_error_flow(
                err_type,
                status_code=resp.status_code,
                current_model=current_model,
                free_models=free_models,
                prompt=prompt,
                wait_seconds=wait_s,
            )

            if action == Action.RETRY_SAME:
                spinner.start()
                continue
            elif action == Action.SWITCH_MODEL and val:
                payload["model"] = val["id"]
                current_model = val
                state.current_model = val
                spinner.start()
                continue
            elif action in (Action.BYPASS_SSL, Action.UPDATE_KEY):
                spinner.start()
                continue
            else:
                return None

        except requests.RequestException as e:
            spinner.stop()
            err_type = classify_error(exc=e)
            wait_s = backoff[min(attempt, len(backoff) - 1)]
            action, val = handle_error_flow(
                err_type,
                exc=e,
                current_model=current_model,
                free_models=free_models,
                prompt=prompt,
                wait_seconds=wait_s,
            )

            if action == Action.RETRY_SAME:
                spinner.start()
                continue
            elif action == Action.SWITCH_MODEL and val:
                payload["model"] = val["id"]
                current_model = val
                state.current_model = val
                spinner.start()
                continue
            elif action in (Action.BYPASS_SSL, Action.UPDATE_KEY):
                spinner.start()
                continue
            elif action == Action.SAVE_DRAFT:
                return None
            else:
                return None

    if resp is None or resp.status_code != 200:
        return None

    render_mode = getattr(state, "render_mode", "panel") if HAS_RICH else "stream"
    full_text = ""
    start_time = time.time()
    header_printed = False
    token_count = 0

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
                            token_count += 1
                            full_text += token

                            if render_mode == "stream":
                                # Live streaming mode: print tokens live to terminal
                                if not header_printed:
                                    spinner.stop()
                                    if HAS_RICH:
                                        console.print("[bold green]Assistant:[/]")
                                    else:
                                        print(f"{Fore.GREEN}Assistant:{Style.RESET_ALL}")
                                    header_printed = True
                                print(token, end="", flush=True)
                            else:
                                # Refined panel mode: update spinner with live token count
                                spinner.update_text(f"Generating response... ({token_count} tokens)")
                except json.JSONDecodeError:
                    continue
    finally:
        spinner.stop()

    elapsed = time.time() - start_time
    full_text = clean_mojibake(full_text)

    # Detect empty responses and trigger recovery
    if not full_text.strip():
        action, val = handle_error_flow(
            ErrorType.EMPTY_RESPONSE,
            current_model=current_model,
            free_models=free_models,
            prompt=prompt,
        )
        if action == Action.SWITCH_MODEL and val:
            payload["model"] = val["id"]
            state.current_model = val
            return stream_response(payload, free_models=free_models)
        elif action == Action.RETRY_SAME:
            return stream_response(payload, free_models=free_models)
        return None

    # Render response cleanly — SINGLE PASS ONLY!
    if render_mode == "panel":
        # Refined mode: render the clean markdown panel ONCE. No duplicate raw stream!
        if HAS_RICH:
            console.print()
            console.print(Panel(
                Markdown(full_text),
                title=f"[bold green]Response[/] [dim]({elapsed:.1f}s • {token_count} tokens • {current_model.get('name', 'AI')})[/]",
                border_style="green",
                box=box.ROUNDED,
            ))
        else:
            print(f"\n{full_text}")
            print(f"\n[Generated in {elapsed:.1f}s • {token_count} tokens]")
    else:
        # Live stream mode: tokens were already printed live, print compact metadata footer
        print()  # newline
        if HAS_RICH:
            console.print(f"[dim](Generated in {elapsed:.1f}s • {token_count} tokens • {current_model.get('name', 'AI')})[/dim]")
        else:
            print(f"\n[Generated in {elapsed:.1f}s • {token_count} tokens]")

    return full_text


def ask_model_isolated(prompt, model_id, max_retries=3):
    """Send a single prompt (no state.conversation history). Used for fan-out & consensus."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {"model": model_id, "messages": [{"role": "user", "content": prompt}]}

    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=get_headers(), json=payload, timeout=60, verify=get_ssl_verify())
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
            err_type = classify_error(exc=e)
            if err_type == ErrorType.SSL_ERROR:
                action, _ = handle_error_flow(err_type, exc=e)
                if action == Action.BYPASS_SSL:
                    continue
                return "Error: SSL certificate verification failed."
            elif err_type == ErrorType.OFFLINE:
                handle_error_flow(err_type, exc=e)
                return "Error: Network connection offline."
            if attempt < max_retries - 1:
                wait = 5 * (2 ** attempt)
                print_warn(f"Request error: {e}. Retrying in {wait}s...")
                time.sleep(wait)
                continue
            return f"Error: {e}"
    return "Error: Failed after all retries."


