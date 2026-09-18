<div align="center">

# Cerebix

**Multi-model AI orchestration for the terminal.**

Route prompts to the best free model. Pit models against each other in debates.
Run collaborative critic-refiner loops. Generate entire codebases. All from one CLI.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![OpenRouter](https://img.shields.io/badge/powered%20by-OpenRouter-purple.svg)](https://openrouter.ai/)

</div>

---

## Why Cerebix?

Most AI terminals lock you into one model. Cerebix treats models as a **team** — routing each prompt to the right specialist, running structured multi-model workflows, and learning your preferences over time.

- **Zero cost.** Strict free-tier validation. Filters out broken or misleadingly tagged models so you never spend API credits.
- **Smart routing.** Classifies prompts by task type (code, math, reasoning, creative) and picks the best available model automatically.
- **Multi-model workflows.** Debate, consensus, fan-out, and critic-refiner loops — all built in.
- **Full project generation.** Describe what you want. Cerebix plans the architecture, generates every file with cross-file awareness, and writes it to disk.

---

## Installation

```bash
git clone https://github.com/YashwanthKumar-K/cerebix.git
cd cerebix
pip install -e .
```

Then run:

```bash
cerebix
```

On first launch, Cerebix opens [OpenRouter Key Settings](https://openrouter.ai/settings/keys) in your browser and prompts you to paste your free API key. It gets saved to `~/.cerebix/config.json` — no environment variables needed.

---

## Commands

### Chat

| Command | Description |
|:--------|:------------|
| *(type anything)* | Chat with the active model |
| `/system <text>` | Set a custom persona or system instruction |
| `/system` | View or clear the current system prompt |
| `/render` | Toggle display mode — `panel` (formatted) vs `stream` (live tokens) |
| `/ssl` | Toggle SSL verification (useful behind proxies or captive portals) |

### Model Selection

| Command | Description |
|:--------|:------------|
| `/select` | Switch to a different model |
| `/models` | List all available free models with context windows |
| `/auto` | Toggle smart auto-routing (picks the best model per task type) |
| `/scores` | View the model performance scorecard |
| `/rate <1-10>` | Rate the last response to improve auto-routing |

### Multi-Model Modes

| Command | Description |
|:--------|:------------|
| `/debate <topic>` | Two models argue opposing sides across rounds, then a judge delivers a verdict |
| `/collab <topic>` | Critic-Refiner loop — one model plans, another critiques with structured feedback, repeat until approved |
| `/consensus <prompt>` | Query multiple models in parallel, then synthesize a single verified answer |
| `/fanout <prompt>` | Broadcast the same prompt to multiple models for side-by-side comparison |

### Project & Context

| Command | Description |
|:--------|:------------|
| `/build <description>` | Plan architecture, generate every file, and write a runnable project to disk |
| `/file <path>` | Load a file into context for review or debugging |
| `/project <path>` | Load an entire folder with automatic secret filtering and an ASCII file tree |

### Session

| Command | Description |
|:--------|:------------|
| `/save` | Save conversation to disk |
| `/load` | Restore a previous conversation |
| `/export` | Export session transcript as Markdown |
| `/savecode` | Extract generated code blocks to files |
| `/tokens` | Show estimated token usage and context utilization |
| `/clear` | Clear conversation history |
| `/exit` | Save and quit |

---

## Multi-Model Workflows

### Debate — `/debate`

Pit two models against each other in a structured, multi-round adversarial debate with stance-forcing and a judicial verdict.

```
/debate Should AI replace software engineers? --style savage --rounds 3
```

Styles: `standard`, `savage`, `dramatic`, `academic`

### Collab — `/collab`

A Critic-Refiner loop. One model generates a plan, another critiques it with structured JSON feedback (confidence score, severity-tagged issues, concrete suggestions). The planner revises until the critic approves or max rounds are hit.

```
/collab Design a REST API for a task manager app
/collab Optimize a web scraper --rounds 3 --threshold 80 --swap
```

Flags:
- `--rounds N` — max iterations (default: 5, max: 10)
- `--threshold N` — confidence score to auto-approve (default: 85)
- `--swap` — swap planner/critic roles halfway through

### Consensus — `/consensus`

Query 2+ models with the same prompt, then have a lead model synthesize their answers into one verified response.

```
/consensus Explain the CAP theorem with real-world examples
```

### Fan-Out — `/fanout`

Send the same prompt to multiple models in parallel for side-by-side comparison.

```
/fanout Write a Python function to merge two sorted lists
```

---

## Configuration

Settings are stored in `~/.cerebix/config.json`:

```json
{
  "openrouter_api_key": "sk-or-v1-..."
}
```

The `OPENROUTER_API_KEY` environment variable takes precedence over the stored key if set.

---

## Requirements

- Python 3.10+
- [OpenRouter](https://openrouter.ai/) API key (free tier works)

Dependencies (installed automatically):

| Package | Purpose |
|:--------|:--------|
| `requests` | HTTP client for OpenRouter API |
| `rich` | Formatted terminal output — panels, tables, markdown |
| `colorama` | Cross-platform ANSI color support |
| `prompt_toolkit` | Interactive autocomplete for slash commands |

---

## License

[MIT](LICENSE) — Yashwanth Kumar K
