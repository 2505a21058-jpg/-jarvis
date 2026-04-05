# JARVIS - Personal AI Assistant with Memory & Smart Browsing

JARVIS is a local AI assistant built for fast conversations, persistent user memory, and practical browser-driven actions.

## Overview

JARVIS is more than a chatbot. It is a small assistant system that combines memory, routing, and actions into a single runtime.

At runtime, JARVIS can:
- maintain short conversational context for fast replies
- preserve core user facts such as identity, role, and health
- route requests into skills such as browsing, opening apps, weather, and time
- perform browser actions through Playwright while keeping the browser session alive

The project is designed to stay lightweight, readable, and fast for local use.

## Features

- Fast Mode: optimized short-term memory using recent conversation with lightweight relevance filtering
- Core Memory: persistent user facts such as name, role, and health stored separately from raw conversation
- Smart Browsing: direct site detection with DuckDuckGo fallback for general requests
- Hybrid Router: intent-based skill execution before LLM fallback
- Safe Shutdown: clean Playwright shutdown and explicit memory summarization on exit

## Memory Architecture

### Fast Mode

Fast Mode uses recent in-memory conversation turns to provide immediate continuity. It is optimized for speed and keeps the context compact.

### Core Memory

Core Memory stores durable user facts such as:
- identity
- role
- health

These facts are persisted in `memory/user_profile.json` and injected into fast mode as a compact user profile block.

### Smart Mode

Smart Mode is planned as a hybrid memory layer that combines recent context with broader relevant memory retrieval.

## Example Usage

```text
You: my name is Shiva Sai Peddi
JARVIS: Got it.

You: i built jarvis
JARVIS: Noted.

You: quit

# Later, after restarting Jarvis

You: who am i
JARVIS: Your name is Shiva Sai Peddi.

You: open github
JARVIS: Opened https://github.com Sir.
```

## Setup

### Requirements

- Python 3.11+
- Ollama installed
- Playwright browser installed

### Installation

```bash
git clone https://github.com/2505a21058-jpg/-jarvis.git
cd -jarvis
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install firefox
python jarvis.py
```

## PROJECT_STRUCTURE

```text
jarvis/
|-- memory/      # Memory system, user profile, structured memory utilities
|-- skills/      # Router and executable skills such as browsing and app actions
|-- jarvis.py    # Main runtime loop and entry point
```

## Roadmap

- [x] Fast memory
- [x] Core memory
- [x] Smart browsing
- [ ] Smart mode
- [ ] Nerd mode

## Notes

JARVIS is currently focused on fast interaction, stable browsing behavior, and a clean memory foundation for future assistant features.
