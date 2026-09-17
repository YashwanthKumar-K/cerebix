# cerebix

A fast, terminal-native AI client built around OpenRouter's free model tier. 

Instead of locking you into a single model, Cerebix auto-routes prompts to the best free specialist (coding, math, reasoning, creative), pits models against each other in structured multi-round debates, and scaffolds entire multi-file codebases from scratch.

---

## Highlights

- **100% Free**: Strict zero-cost validation. Filters out broken or misleadingly tagged models so you never spend API credits.
- **Smart Auto-Routing (`/auto`)**: Classifies prompts and routes coding tasks to code models, reasoning tasks to math/logic models, and creative writing to high-temperature models. Learns your preferences over time via `/rate`.
- **Multi-Agent Debate (`/debate`)**: Pit two models against each other in an adversarial, multi-turn clash (Affirmative vs Negative). Each round rebuts the opponent's exact arguments before an impartial judge model delivers a verdict.
- **Consensus & Fan-Out (`/consensus`, `/fanout`)**: Query multiple models in parallel to eliminate hallucinations and synthesize a unified answer.
- **Project Builder (`/build`)**: Give it a specification. Cerebix plans the architecture, generates each file with cross-file signature awareness, and writes a runnable project to disk.
- **Codebase Context (`/project`, `/file`)**: Ingest whole folders or single files with automatic secret stripping (`.env`, `.pem`, cloud credentials) and visual ASCII file trees.
- **Interactive Autocomplete**: Type `/` for a live, searchable command palette powered by `prompt_toolkit`.

---

## Quickstart

### Installation

Requires Python 3.10+.

```bash
git clone https://github.com/YashwanthKumar-K/cerebix.git
cd cerebix
pip install -e .
```

### Running

```bash
cerebix
```

On first launch, if no API key is found, Cerebix opens the [OpenRouter Key Settings](https://openrouter.ai/settings/keys) in your browser and prompts you to paste your free key directly into the terminal. It gets saved to `~/.cerebix/config.json` automatically — no environment variable setup needed.

*(Alternatively, you can export `OPENROUTER_API_KEY="sk-or-v1-..."` in your shell).*

---

## Commands

| Command | Usage | Description |
|:---|:---|:---|
| `/auto` | `/auto` | Toggle smart task-based auto-routing on/off |
| `/debate` | `/debate <topic> [--style ...] [--rounds 2-4]` | Two models debate opposing sides with a judge verdict |
| `/consensus` | `/consensus <prompt>` | Query multiple models in parallel and synthesize a single verified answer |
| `/fanout` | `/fanout <prompt>` | Broadcast prompt to multiple models for side-by-side comparison |
| `/build` | `/build <description>` | Architect and generate a full multi-file project to disk |
| `/file` | `/file <path> [instruction]` | Load a file into context for review or debugging |
| `/project` | `/project <path> [instruction]` | Load an entire repository with secret filtering and an ASCII tree |
| `/models` | `/models` | Display live table of available free models and context windows |
| `/select` | `/select` | Switch active model manually |
| `/system` | `/system [persona]` | View, set, or clear system prompt |
| `/rate` | `/rate <1-10>` | Rate the last response to train your local auto-routing scorecard |
| `/scores` | `/scores` | View historical model scorecard by category |
| `/savecode` | `/savecode` | Extract generated code blocks to collision-safe files |
| `/tokens` | `/tokens` | Inspect estimated token usage and context utilization |
| `/save` | `/save` | Save conversation state to disk |
| `/load` | `/load` | Restore previous conversation state |
| `/export` | `/export` | Export session transcript to formatted Markdown |
| `/clear` | `/clear` | Clear conversation history |
| `/exit` | `/exit` | Save and quit |

---

## Configuration

Settings are stored in `~/.cerebix/config.json`:

```json
{
  "openrouter_api_key": "sk-or-v1-..."
}
```

Environment variables always take precedence if defined:
- `OPENROUTER_API_KEY`: overrides the stored key in `config.json`.

---

## License

[MIT](LICENSE)
