import re
from datetime import datetime
from .config import print_warn, print_info, print_success, print_error

def extract_code_blocks(text):
    return re.findall(r"```(\w*)\n(.*?)```", text, re.DOTALL)


def save_code_interactive(last_response):
    blocks = extract_code_blocks(last_response)
    if not blocks:
        print_warn("No code blocks found in the last response.")
        return

    if len(blocks) == 1:
        selected = [0]
    else:
        print_info(f"Found {len(blocks)} code block(s):")
        for i, (lang, code) in enumerate(blocks):
            preview = code.strip()[:80].replace("\n", " ")
            print_info(f"  [{i}] ({lang or 'text'}) {preview}...")
        raw = input("Which to save? (comma-separated or 'all'): ").strip()
        if raw.lower() == "all":
            selected = list(range(len(blocks)))
        else:
            try:
                selected = [int(x.strip()) for x in raw.split(",")]
            except ValueError:
                print_error("Invalid selection.")
                return

    for idx in selected:
        if 0 <= idx < len(blocks):
            lang, code = blocks[idx]
            ext = lang.lower() if lang and lang != "plain" else "txt"
            fname = f"generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx}.{ext}"
            with open(fname, "w", encoding="utf-8") as f:
                f.write(code)
            print_success(f"Saved block [{idx}] ({lang or 'text'}) -> {fname}")


