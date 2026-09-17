import sys
import time
import threading
from .config import HAS_RICH, console

# Rotating messages shown during Phase 1 (architecture planning)
_PLAN_MESSAGES = [
    "Thinking...",
    "Brainstorming structure...",
    "Architecting your project...",
    "Designing file layout...",
    "Planning dependencies...",
    "Mapping out the codebase...",
    "Consulting the blueprint...",
    "Evaluating tech stack...",
    "Sketching the architecture...",
    "Thinking about file structure...",
]

# Rotating messages shown during Phase 2 (per-file code generation)
_CODE_MESSAGES = [
    "Writing code...",
    "Crafting functions...",
    "Building the logic...",
    "Connecting the pieces...",
    "Generating implementation...",
    "Wiring up imports...",
    "Filling in the details...",
    "Adding finishing touches...",
    "Cooking up some code...",
    "Assembling the module...",
]

# Rotating messages shown during normal chat response generation
_CHAT_MESSAGES = [
    "Thinking...",
    "Formulating response...",
    "Consulting model...",
    "Connecting thoughts...",
    "Reasoning through prompt...",
    "Drafting answer...",
    "Synthesizing knowledge...",
]

# Rotating messages shown during debate rounds
_DEBATE_MESSAGES = [
    "Formulating arguments...",
    "Analyzing opponent's points...",
    "Drafting rebuttal...",
    "Sharpening counterpoints...",
    "Reviewing debate flow...",
    "Preparing next speech...",
]

# Rotating messages shown during Chief Justice deliberation
_JUDGE_MESSAGES = [
    "Evaluating debate arguments...",
    "Reviewing round transcripts...",
    "Deliberating verdict...",
    "Scoring logic and rebuttals...",
    "Weighing persuasive points...",
    "Finalizing judicial scorecard...",
]

# Rotating messages shown during consensus and fanout synthesis
_SYNTHESIS_MESSAGES = [
    "Synthesizing responses...",
    "Resolving contradictions...",
    "Evaluating evidence...",
    "Consolidating consensus...",
    "Drafting unified answer...",
]

# Rotating messages shown during parallel queries
_PARALLEL_MESSAGES = [
    "Querying models in parallel...",
    "Waiting for model responses...",
    "Gathering candidate answers...",
    "Streaming multi-model insights...",
]


class ThinkingSpinner:
    """An animated, non-blocking terminal spinner with rotating status messages.

    Supports both context manager (`with ThinkingSpinner(messages):`)
    and manual lifecycle (`spinner.start()`, `spinner.stop()`).
    """

    FRAMES_UNICODE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    FRAMES_ASCII = ["|", "/", "-", "\\"]

    def __init__(self, messages=None, interval=0.08, rotate_every=2.5):
        self.messages = list(messages) if messages else ["Thinking..."]
        self.interval = interval
        self.rotate_every = rotate_every
        self.stop_event = threading.Event()
        self.thread = None
        self.start_time = 0
        self._running = False
        self.dynamic_text = None

    def update_text(self, text):
        """Dynamically override the spinner label (e.g. for live token counts)."""
        self.dynamic_text = text

    def _spin(self):
        try:
            "⠋".encode(sys.stdout.encoding or "utf-8")
            frames = self.FRAMES_UNICODE
        except Exception:
            frames = self.FRAMES_ASCII

        frame_idx = 0
        last_len = 0

        while not self.stop_event.wait(self.interval):
            elapsed = time.time() - self.start_time
            if self.dynamic_text:
                msg = self.dynamic_text
            else:
                msg_idx = int((elapsed // self.rotate_every) % len(self.messages))
                msg = self.messages[msg_idx]
            frame = frames[frame_idx % len(frames)]
            frame_idx += 1

            styled_text = f"\r\033[36m{frame}\033[0m \033[1;36m{msg}\033[0m \033[90m({elapsed:.1f}s)\033[0m"
            plain_len = len(frame) + 1 + len(msg) + 1 + len(f"({elapsed:.1f}s)")
            pad = max(0, last_len - plain_len)
            last_len = plain_len

            try:
                sys.stdout.write(styled_text + " " * pad)
                sys.stdout.flush()
            except Exception:
                break

    def start(self):
        """Start the background spinner animation."""
        if self._running:
            return self
        self._running = True
        self.dynamic_text = None
        self.stop_event.clear()
        self.start_time = time.time()
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        """Stop the spinner and erase the spinner line completely."""
        if not self._running:
            return
        self._running = False
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.4)
        try:
            sys.stdout.write("\r" + " " * 80 + "\r")
            sys.stdout.flush()
        except Exception:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def _thinking_spinner(messages):
    """Context manager wrapper for backward compatibility with build.py and callers."""
    return ThinkingSpinner(messages)



