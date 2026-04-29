<div align="center">

# 🤖 JARVIS
### Personal AI Operating System — Local First, Always

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square&logo=python)](https://python.org)
[![Ollama](https://img.shields.io/badge/Powered%20by-Ollama-black?style=flat-square)](https://ollama.ai)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-47%20passing-brightgreen?style=flat-square)](tests/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)]()

**Jarvis is a local-first autonomous AI agent that lives on your machine.**  
No cloud. No subscription. No data leaving your device.  
It understands natural language, executes real computer tasks, learns your workflows, and gets smarter over time.

[Quick Start](#quick-start) • [Features](#features) • [Architecture](#architecture) • [Teaching Jarvis](#teaching-jarvis-new-skills) • [Remote Control](#remote-control) • [Contributing](#contributing)

</div>

---

## What Jarvis Can Do
✅ Open apps and websites by name         → "open chrome" / "open gmail"
✅ Search the web                          → "search for python tutorials"
✅ Search your local files and folders     → "find folder Spider Man Remastered"
✅ Type text into any application          → "type hello world"
✅ Browse to any URL                       → "go to github.com"
✅ Send emails via SMTP                    → "send email to john@..."
✅ Read and summarize PDF/text files       → "read report C:\docs\report.pdf"
✅ Open Cursor or VS Code                  → "open cursor"
✅ Monitor RAM/CPU and alert on thresholds → "alert me if RAM goes above 80%"
✅ Set real timed reminders                → "remind me in 5 minutes to check my code"
✅ Answer questions and hold conversations → "explain quantum entanglement"
✅ Learn new skills from plain English     → "teach you how to open my morning workflow"
✅ Remember context across sessions        → memory persists between restarts
✅ Control from your phone                 → Telegram bot or WebSocket
✅ Proactively notify you of patterns      → monitors downloads, tasks, and memory

---

## Quick Start

### Prerequisites

| Requirement | Version | Install |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| Ollama | Latest | [ollama.ai](https://ollama.ai) |
| Git | Any | [git-scm.com](https://git-scm.com) |

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/jarvis.git
cd jarvis
python -m pip install -r requirements.txt
python -m pip install psutil
```

### 2. Pull the required models

```bash
# Main language model (required)
ollama pull mistral

# OR use llama3.2 if you prefer
ollama pull llama3.2:3b

# Semantic memory model (optional but recommended)
ollama pull nomic-embed-text

# Vision model for screen understanding (optional)
ollama pull llava
```

### 3. Run Jarvis

```bash
python jarvis.py
```

You will see:
✅ Ollama is ready
✅ 7 built-in skills registered
✅ Gate layer initialized
JARVIS Online
Welcome back.
You: _

### 4. Try some commands
You: open chrome
You: search for python tutorials
You: what is machine learning?
You: remind me in 5 minutes to take a break
You: find folder Documents on my pc
You: teach you how to open my email: open chrome, then go to gmail.com

---

## Features

### Three-Tier Intelligence Routing

Every input passes through three layers — fastest first. Most common commands
never touch the LLM at all.
Input: "open chrome"
│
▼ TIER 1 — Gate Layer (0ms, zero LLM)
Regex pattern matches → executes directly
Resolves ~60% of all inputs
│
▼ TIER 2 — Fast Decide (300–600ms, 1 LLM call)
Minimal prompt, classifies chat vs action
Resolves simple questions and intent
│
▼ TIER 3 — Full Reasoning (800–2000ms, 1–2 LLM calls)
Full context + memory + conversation history
Handles complex tasks, planning, teaching

**Result:** Simple commands feel instant. Complex tasks get full reasoning.

---

### Skill System

Every capability is a **Skill** — a self-contained unit with a name, description,
and execute function.

**Built-in Skills**

| Skill | Trigger Examples | What It Does |
|---|---|---|
| `open_app` | "open chrome", "launch vscode" | Opens desktop apps and web services |
| `browse` | "go to github.com" | Navigates browser to URL |
| `type_text` | "type hello world" | Types text via keyboard automation |
| `search` | "search for cats" | Web search |
| `system_search` | "find folder jarvis on my pc" | Searches local filesystem |
| `system_monitor` | "monitor my RAM above 70%" | Real-time resource monitoring |
| `reminder` | "remind me in 5 min to check code" | Timed notifications |
| `send_email` | "send email to..." | SMTP email sending |
| `read_report` | "summarize report.pdf" | PDF and text file reading |
| `launch_claude_code` | "open cursor" | Opens AI code editors |
| `list_skills` | "what can you do" | Lists all available skills |

---

### Skill Learning

Teach Jarvis new composite skills in plain English. They persist across sessions
and get faster over time.
You: teach you how to open my morning workflow:
open chrome, then go to gmail.com, then open vscode
JARVIS: Learned new skill: 'open_morning_workflow'
— Opens Chrome, Gmail, and VS Code

---

### Memory System

Jarvis remembers context across sessions using a three-tier memory architecture.
recent.jsonl  
long_term.jsonl  
experiences.jsonl  

---

### Proactive Heartbeat

Jarvis monitors your system in the background.

---

### Remote Control

Control Jarvis from your phone using Telegram or WebSocket.

---

## Architecture

jarvis.py  
agent/  
memory/  
skills/  
models/  
interfaces/  

---

## Environment Variables

JARVIS_MODEL=mistral  
JARVIS_REMOTE_BRIDGE=false  
JARVIS_HEARTBEAT=true  
JARVIS_HEARTBEAT_INTERVAL=600  

---

## Teaching Jarvis New Skills

teach you how to open dev setup:
open vscode, then open chrome, then go to localhost:3000

---

## Running Tests

```bash
pytest tests/ -v
pytest tests/ -v --cov=agent --cov=memory --cov=skills --cov-report=term-missing
pytest tests/test_gate.py -v
```

---

## Project Structure

jarvis/  
agent/  
memory/  
models/  
skills/  
interfaces/  
tests/  

---

## Known Limitations

| Limitation | Status | Workaround |
|---|---|---|
| Memory recall is keyword-based (TF-IDF) | Improving | Use embeddings |
| No GUI | Planned | Use Telegram |
| Limited app discovery | Improving | Add manually |

---

## Roadmap

V2.1 — Current  
V2.5 — In Progress  
V3.0 — Planned  

---

## Contributing

1. Fork the repository  
2. Create branch  
3. Make changes  
4. Run tests  
5. Open PR  

---

## License

MIT License  

---

<div align="center">

**Built with Python + Ollama**  
*Local first. Always.*

