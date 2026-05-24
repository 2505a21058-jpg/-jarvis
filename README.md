# Jarvis — Local-First Desktop AI Assistant

Full PC automation, screen perception, web research, and memory — 100% local, zero cloud dependency.

```
                                  User Input
                              (stdin / Web / Telegram)
                                     │
                                     ▼
     ┌──────────────────── Intent System ───────────────────┐
     │  31 intents  classifier (rule → LLM) → router       │
     │                     │                                │
     │  ┌──────────────────┼──────────────────┐             │
     │  ▼                  ▼                  ▼             │
     │ Skills (27)   ComputerUseAgent    Deep Research     │
     │ executor(      │                    │               │
     │  retry,timeout, ├─ RawVision        ├─ decompose    │
     │  hooks,policy)  ├─ Hands            ├─ parallel     │
     │                 └─ ScreenshotAgent  └─ synthesize   │
     │                                                     │
     │          Models (Ollama — all local)                │
     └─────────────────────────────────────────────────────┘
```

## Features

| Capability | Description |
|---|---|
| **Computer Use** | Perceive → plan → act → verify loop. 6-layer screen perception (UIA, CDP, OCR, pixel diff, process monitor, screenshot) + 5 action engines (CDP, UIA, WinAPI, SendInput, Terminal). Falls back to ScreenshotAgent (screenshot + OCR + vision) when accessibility layers are unavailable |
| **Intent System** | 31 classified intents via rule-based + LLM pipeline. Each intent maps to a skill with extracted entities |
| **Web Research** | DuckDuckGo search → trafilatura content extraction → LLM synthesis with source citations. Deep research mode: generates 4 sub-questions, searches in parallel, merges results |
| **Codebase Explorer** | Ask questions about Jarvis's own source code. Static mode: grep + read + import tracing. Runtime mode: `importlib` + `inspect.getmembers` with safety guards |
| **Memory** | 3-tier JSONL storage (recent / long-term / experiences) with BM25 + TF-IDF + embedding vector search, importance scoring, TTL pruning, and personal facts |
| **Multi-Interface** | CLI stdin loop, FastAPI web UI with SPA, Telegram bot bridge, WebSocket bridge |
| **Configuration** | 19-section typed config via YAML + 135+ environment variable overrides. Runtime persistence |
| **Permissions** | 3-mode policy engine: allow_all, deny_all, confirm_all. Per-skill rules with restricted params |
| **All Local** | All models run through Ollama. DuckDuckGo search needs no API key. Windows-native automation via UIA + WinAPI + CDP + SendInput |

## Quick Start

```bash
# Install with all optional features
pip install -e ".[windows,hands,ocr,dev]"

# Run full test suite (393 tests)
pytest tests/ -q

# Start Jarvis CLI
python -m jarvis

# Start with web UI at http://127.0.0.1:9090
python -m jarvis --web

# Single-shot mode
python -m jarvis "open notepad and type hello"
```

### RawVision Quick Start

```bash
pip install rawvision
```

```python
from rawvision import RawVision

screen = RawVision.capture()
print(screen.to_llm())
```

## Requirements

- Python 3.11+
- [Ollama](https://ollama.ai) with models (default: `gemma3:4b`, `nomic-embed-text`)
- Windows 10/11 (UIA, WinAPI, SendInput engines are Windows-native)

## Installation

### Core

```bash
pip install -e .
```

### Optional Groups

```bash
pip install -e ".[windows]"     # comtypes, pywinauto, dxcam, pywin32
pip install -e ".[hands]"       # keyboard library
pip install -e ".[ocr]"         # paddleocr / easyocr for ScreenshotAgent
pip install -e ".[dev]"         # pytest, build
pip install -e ".[all]"         # everything
```

### Pull Ollama Models

```bash
ollama pull gemma3:4b           # primary vision + text model
ollama pull nomic-embed-text    # memory embeddings
ollama pull moondream           # alternative vision model
ollama pull llama3.2:3b         # lightweight text model
```

## Intent System — 31 Capabilities

Every user input is classified into one of 31 intents via a pipeline: learned rules → trivial patterns → config → email → reminders → system → computer use → open patterns → browse → GUI → web search → file search → run code → list skills → web summary → deep research → codebase explore → LLM fallback.

| Intent | Example Input | Target Skill |
|---|---|---|
| `SYSTEM_CHECK` | "check my cpu usage" | `system_monitor` |
| `OPEN_APP` | "open chrome" | `open_app` |
| `OPEN_AND_SEARCH` | "open youtube and search for lofi" | `open_and_search` |
| `OPEN_AND_TYPE` | "open notepad and type hello" | `open_and_type` |
| `OPEN_AND_PLAY` | "open youtube search songs and play first" | `open_search_and_play` |
| `WEB_BROWSE` | "go to github.com" | `browse` |
| `WEB_SEARCH` | "search python tutorials" | `browse` |
| `WEB_SUMMARY` | "tell me about elon musk" | `web_summary` |
| `COMPOSE_EMAIL` | "send email to john@example.com" | `compose_email` |
| `SET_REMINDER` | "remind me in 5 minutes" | `reminder` |
| `RUN_CODE` | "run a python script to rename files" | `run_code` |
| `FILE_SEARCH` | "find notes.txt on my pc" | `system_search` |
| `WEATHER` | "what is the weather in Hyderabad" | `weather` |
| `PNR` | "check PNR 1234567890" | `pnr` |
| `TRAIN` | "where is train 12345" | `train` |
| `GUI_CLICK` | "click the submit button" | `gui_automate` |
| `COMPUTER_USE` | "go to spotify and create a party playlist" | `computer_control` |
| `CODABASE_EXPLORE` | "how does the screenshot agent work" | `codebase_explorer` |
| `DEEP_RESEARCH` | "compare jarvis screenshot mode to claude cc" | `deep_research` |
| `CHAT` | "what is machine learning" | `respond` |

## Architecture

### RawVision — Screen Perception

Reads semantic UI state from the operating system instead of raw pixels. Returns a `ScreenContext` with structured elements, roles, bounds, and text.

| Layer | Backend | Purpose |
|---|---|---|
| 0 — Process Monitor | psutil + win32 | Foreground app metadata, PID, window title, CDP port |
| 1 — UIA | Windows UI Automation | Full accessibility tree with roles, bounds, automation IDs |
| 2 — CDP / DOM | Chrome DevTools Protocol | DOM tree from Chrome / Electron apps |
| 3 — Pixel Diff | numpy + Pillow | Changed framebuffer regions between captures |
| 4 — CV / OCR | OpenCV | Text detection on changed regions |
| 5 — Screenshot | mss | Base64 PNG fallback for vision models |

```python
from rawvision import RawVision

vision = RawVision()
screen = vision.capture()          # runs all layers in parallel
print(screen.to_llm())             # formatted for LLM consumption
element = screen.find("Search")    # locate by name
```

### Hands — Action Engines

Routes actions to the safest available engine through a fallback chain.

| Engine | Backend | When Used |
|---|---|---|
| CDP | Chrome DevTools Protocol | Browser / Electron elements with CDP node ID |
| UIA | Windows UI Automation | Elements with automation_id or runtime_id |
| WinAPI | win32gui / win32api | Elements with HWND |
| Terminal | subprocess | Shell commands |
| SendInput | Win32 SendInput | Coordinates-only fallback (DPI-correct) |

```python
from agent.hands import HandsController

hands = HandsController()
hands.click(element)               # routes to best engine automatically
```

### ComputerUseAgent — Full Perception Loop

Combines RawVision + Hands + a local vision planner into a perceive→plan→act→verify cycle.

```python
from agent.computer_use import ComputerUseAgent

agent = ComputerUseAgent(max_steps=8)
result = agent.run("open the Save dialog and confirm")
print(result.final_reason)
```

When RawVision returns no structural data (no UIA, no CDP, no app name), the agent auto-falls back to ScreenshotAgent.

### ScreenshotAgent — Screenshot-Only Fallback

Claude Computer Use–equivalent fallback when no accessibility layers are available:

1. **Perception**: `mss` screenshot → PaddleOCR/EasyOCR → Gemma3/LLaVa description → `ScreenRepr` with auto-zoom on low-confidence text
2. **Planner**: Vision model selects next action (click, type, key, scroll, wait, zoom, done, fail) using OCR coordinates
3. **Executor**: `pyautogui` → SendInput fallback chain, captures before/after for verification
4. **Verifier**: Pixel diff + vision model double-check

### Deep Research — Multi-Query Parallel Search

```python
from internet.deep_research import deep_research

answer = deep_research("compare open source computer use agents", format="table")
```

1. **Decompose**: LLM generates 4 sub-questions covering different angles
2. **Parallel Search**: Each sub-question searches DuckDuckGo concurrently
3. **Fetch**: Results deduplicated, top pages fetched via trafilatura
4. **Synthesize**: LLM composes comprehensive answer with source citations

Output format auto-detects from query: `compare` → table, `list` → bullets, `explain` → sections.

### Codebase Explorer — Introspect Jarvis Itself

Two modes:
- **read** (default): Greps `.py` files → reads source code → traces AST import chains → LLM answers
- **runtime**: `importlib.import_module` → `inspect.getmembers` classes/functions

Safety: restricted to `agent/`, `skills/`, `internet/`, `memory/`, `permissions/`, `jconfig/` prefixes. Blocks `os.system`, `subprocess`, `eval`, `exec`, `shutil.rmtree`.

```python
from skills.codebase_explorer import CodebaseExplorerSkill

explorer = CodebaseExplorerSkill()
result = explorer.execute({"query": "how does the executor handle timeouts", "mode": "read"}, None)
```

## Skills Reference

27 built-in skills registered at startup:

| Skill Name | Description | Timeout |
|---|---|---|
| `open_app` | Launch desktop apps | 30s |
| `type_text` | Type into active window | 10s |
| `browse` | Playwright web browsing | 45s |
| `open_and_search` | Open app + search within | 45s |
| `open_and_type` | Open app + type text | 25s |
| `open_search_and_play` | Open app + search + play | 60s |
| `compose_email` | Compose email in browser | 10s |
| `send_email` | SMTP email | 10s |
| `web_summary` | Research + synthesize | 50s |
| `web_search` | Quick web search | 45s |
| `deep_research` | Multi-query research | 90s |
| `computer_control` | Desktop automation | 60s |
| `codebase_explorer` | Codebase questions | 45s |
| `gui_automate` | Click/type via accessibility | 10s |
| `run_code` | Python code execution | 10s |
| `system_monitor` | CPU/RAM/disk/GPU | 8s |
| `system_search` | Find files/folders | 10s |
| `reminder` | Timer notifications | 5s |
| `weather` | OpenWeatherMap | 10s |
| `pnr` | Indian Railway PNR | 10s |
| `train` | Live train status | 10s |
| `respond` | LLM chat | 15s |
| `list_skills` | List all skills | 3s |
| `read_report` | Read/analyze files | 10s |
| `launch_claude_code` | Launch Claude Code | 10s |
| `quick_search` | Fast search snippets | 30s |
| `learn_skill` | Teach new skills | — |

## Memory System

Three JSONL-backed tiers with automatic importance scoring and lifecycle management:

| Tier | File | Max Entries | Purpose |
|---|---|---|---|
| Short-term | `recent.jsonl` | 200 | Recent conversation turns |
| Long-term | `long_term.jsonl` | 2,000 | Important persisted knowledge |
| Experiences | `experiences.jsonl` | 500 | Learned interactions |

**Retrieval modes**: `full` (BM25 + TF-IDF + importance + token budget), `fast` (recent + relevance), `semantic` (Ollama embedding vectors), `tags`, `deep`, `recent`.

**Personal facts**: Dedicated `personal_facts.jsonl` — never pruned, pattern-extracted user preferences.

```python
from memory.core import Memory

mem = Memory()
results = mem.retrieve("what did we discuss about the executor", mode="semantic")
```

## Configuration

### `jconfig.yaml` (optional — overrides defaults)

```yaml
llm:
  main_model: gemma3:4b
  ollama_host: http://localhost:11434
  timeout: 18

memory:
  max_entries: {recent: 200, long_term: 2000, experiences: 500}

executor:
  max_retries: 2
  backoff_ms: 200
  vision_verify: false
```

### Environment Variables

135+ `JARVIS_*` vars mapped to config sections. Key ones:

| Variable | Default | Description |
|---|---|---|
| `JARVIS_MODEL` | gemma3:4b | Primary LLM |
| `JARVIS_FAST_MODEL` | llama3.2:3b | Lightweight model |
| `JARVIS_VISION_MODEL` | gemma3:4b | Vision model |
| `JARVIS_EMBED_MODEL` | nomic-embed-text | Embedding model |
| `JARVIS_OLLAMA_HOST` | http://localhost:11434 | Ollama endpoint |
| `JARVIS_VISION_VERIFY` | false | Enable visual verification |
| `JARVIS_EXECUTOR_TIMEOUT` | 10 | Default skill timeout |
| `JARVIS_MEMORY_MODE` | full | Default retrieval mode |
| `JARVIS_WEB_HOST` | 127.0.0.1 | Web UI bind address |
| `JARVIS_WEB_PORT` | 9090 | Web UI port |

## Permissions

3-mode policy engine (`permissions/policy.json`):

| Mode | Behavior |
|---|---|
| `allow_all` (default) | All skills run without confirmation |
| `deny_all` | All skills blocked |
| `confirm_all` | User must confirm each execution |

Per-skill rules can override the mode. High-risk skills (`send_email`, `run_code`, `computer_control`) require confirmation by default.

```bash
set JARVIS_PERMISSION_MODE=confirm
```

## User Interfaces

### CLI (default)

```bash
python -m jarvis
# You> check my cpu usage
```

### Web UI

```bash
python -m jarvis --web
# Open http://127.0.0.1:9090 in browser
```

Full dev board: model status, browser health, vision backends, automation engines, network status, memory stats.

### Telegram Bridge

Set `JARVIS_TELEGRAM_BOT_TOKEN` and optionally `JARVIS_TELEGRAM_CHAT_ID` for phone-to-desktop control.

## Project Structure

```
jarvis/
├── agent/                  # Core agent layer
│   ├── intent/             # Intent schema, classifier, router, rules
│   ├── hands/              # Action engines (CDP, UIA, WinAPI, SendInput, Terminal)
│   ├── screenshot_agent/   # Screenshot-only fallback agent
│   ├── harness/            # Evaluation harness
│   ├── loop.py             # Main agent cycle
│   ├── executor.py         # Skill execution with retry/timeout/hooks
│   ├── computer_use.py     # Full computer-use agent
│   ├── planner.py          # DAG-based multi-step planner
│   └── state.py            # Conversation state
│
├── skills/                 # 27 skill implementations
│   ├── automation/         # PC, browser, hero automation subsystems
│   ├── base.py             # SkillBase / SkillResult
│   ├── registry.py         # SkillRegistry
│   └── *.py                # Individual skills
│
├── rawvision/              # Screen perception library
│   ├── capture/            # 6 capture layers
│   ├── fusion/             # Arbitrator, deduplicator, formatter
│   ├── output/             # ScreenContext, UIElement schema
│   └── utils/              # Spatial, timeout utils
│
├── internet/               # Web research
│   ├── search.py           # DuckDuckGo HTML search
│   ├── fetch.py            # trafilatura content extraction
│   ├── synthesize.py       # LLM synthesis with citations
│   ├── deep_research.py    # Multi-query parallel research
│   └── web_agent.py        # Research orchestrator
│
├── memory/                 # Memory system
│   ├── core.py             # 3-tier storage + retrieval
│   ├── index.py            # BM25 search index
│   ├── persistent_index.py # Embedding index
│   └── personal_facts.py   # User preferences
│
├── models/                 # LLM layer
│   ├── llm.py              # Unified LLM calls (text, JSON, cached, fast)
│   ├── gemma.py            # Gemma3 client (text + vision)
│   └── model_router.py     # Intent-to-model routing
│
├── jconfig/                # Configuration system
│   ├── schema.py           # 19 typed config dataclasses
│   └── loader.py           # YAML + env var loader
│
├── permissions/            # Policy engine
│   └── policy.py           # allow/deny/confirm with rules
│
├── interfaces/             # User interfaces
│   ├── web/                # FastAPI + SPA
│   └── remote_bridge.py    # Telegram + WebSocket
│
├── utils/                  # Logging, helpers
├── tests/                  # 393 tests across 65 files
├── config.py               # Legacy env config (backward compat)
├── jconfig.yaml            # YAML config file
└── pyproject.toml          # Package configuration
```

## Testing

```bash
# Full suite (393 tests)
pytest tests/ -q

# Specific subsystems
pytest tests/test_rawvision_*.py -q           # Screen perception
pytest tests/test_hands_*.py -q               # Action engines
pytest tests/test_internet_access.py -q        # Web research
pytest tests/test_codebase_deep_research.py -q # Codebase explorer + deep research
pytest tests/test_skills/ -q                   # Individual skill tests
pytest tests/test_screenshot_agent.py -q       # ScreenshotAgent

# With full output
pytest tests/ -v
```

## Adding a New Skill

1. **Define intent** in `agent/intent/schema.py` — add to `IntentName` enum and `INTENT_CATALOG`
2. **Route** in `agent/intent/router.py` — map intent to skill name
3. **Classify** in `agent/intent/rules.py` — add pattern rules (or rely on LLM fallback)
4. **Implement** a skill class extending `SkillBase` in `skills/`
5. **Register** in `skills/__init__.py` — import and call `registry.register_builtin()`
6. **Set timeout** in `agent/executor.py` — add to `_SKILL_TIMEOUT_OVERRIDES`
7. **Test** — create tests in `tests/` or `tests/test_skills/`

## License

MIT
