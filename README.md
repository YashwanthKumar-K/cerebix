# 🧠 Cerebix

<div align="center">

```
   ____ _____ ____  _____ ____  ______  __
  / ___| ____|  _ \| ____| __ )|_ _\ \/ /
 | |   |  _| | |_) |  _| |  _ \ | | \  / 
 | |___| |___|  _ <| |___| |_) || | /  \ 
  \____|_____|_| \_\_____|____/|___/_/\_\
```

**The Ultimate Multi-Model AI Orchestration CLI — 100% Free**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Powered by OpenRouter](https://img.shields.io/badge/API-OpenRouter-purple.svg)](https://openrouter.ai/)
[![Rich CLI](https://img.shields.io/badge/UI-Rich-green.svg)](https://github.com/Textualize/rich)

</div>

---

## 💡 Why Cerebix is the Best AI CLI

Most AI tools lock you into a single paid provider. **Cerebix is different.** It connects to OpenRouter and leverages a collaborative fleet of **20+ 100% free AI models**, orchestrating them dynamically based on what you need. 

*   **Zero Cost Guarantee**: Cerebix strictly filters and validates models using the `:free` suffix, blocking accidental charges globally.
*   **Intelligent Auto-Routing**: Why ask a math model to write poetry? Cerebix automatically classifies your prompt and routes it to the highest-scoring model for that specific category (Coding, Reasoning, Creative, etc.).
*   **Security First**: Built-in safeguards automatically strip sensitive secrets (`.env`, `.pem`, `id_rsa`) before uploading project context, and path-traversal protection strictly sandboxes generated project files.
*   **Beautiful UI**: Animated thinking spinners, live token generation times (e.g. `(4.2s)`), and syntax-highlighted markdown rendering make the terminal feel like a native app.
*   **Frictionless Setup**: Missing an API key? Cerebix detects it and automatically launches your web browser directly to the exact page you need.

---

## ✨ Core Features

*   🔄 **Smart Auto-Routing:** Analyzes your prompt and automatically routes it to the best specialist model.
*   ⚖️ **Consensus / Jury Mode (`/consensus`):** Queries 3+ models in parallel, compares responses, and synthesizes a unified consensus answer to eliminate hallucinations.
*   🚀 **Parallel Fan-Out (`/fanout`):** Dispatches the exact same query to multiple models concurrently for side-by-side comparison.
*   🏗️ **Project Builder (`/build`):** Feed it an idea, and Cerebix will architect the file structure, generate every file simultaneously with cross-file awareness, and safely write the entire project to your local disk.
*   📂 **Codebase Context (`/project` & `/file`):** Ingest individual files or entire project directories seamlessly.
*   ⭐️ **Interactive Scorecard (`/rate`):** Rate model answers from 1-10 to build a personalized, persistent local scorecard that improves your Auto-Routing engine over time.
*   💾 **Code Extractor (`/savecode`):** Automatically detects and exports generated code blocks to collision-safe files with a single command.

---

## ⚡ Installation & Setup

Cerebix is packaged as a standard, globally accessible Python module.

### 1. Clone & Install
```bash
git clone https://github.com/YashwanthKumar-K/cerebix.git
cd cerebix
pip install -e .
```
*(This automatically installs dependencies like `requests` and `rich`, and links the `cerebix` command to your system).*

### 2. Start Cerebix
Just open your terminal from anywhere and run:
```bash
cerebix
```

*(If you don't have an OpenRouter API key configured yet, Cerebix will automatically open your browser to the key creation page and show you how to set it!)*

---

## 📚 Command Reference

| Command | Description |
| :--- | :--- |
| **`/auto`** | Toggle Smart Auto-Routing ON/OFF |
| **`/consensus <prompt>`** | Run multi-model jury voting and synthesis |
| **`/fanout <prompt>`** | Query multiple models in parallel |
| **`/build <description>`** | Plan + generate a full multi-file project to disk |
| **`/models`** | List all available free models |
| **`/select`** | Manually switch your active model |
| **`/rate <1-10>`** | Rate the model's last answer to improve auto-routing |
| **`/scores`** | View model performance scorecard |
| **`/system <text>`** | Set a custom persona / system instruction |
| **`/file <path>`** | Attach a single file into the prompt |
| **`/project <path>`** | Ingest an entire project folder |
| **`/savecode`** | Extract and save generated code blocks to disk |
| **`/clear`** | Clear conversation history |
| **`/exit`** | Save session and exit |

---

## 📜 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
