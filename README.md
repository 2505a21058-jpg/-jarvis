# JARVIS — Open Source AI Assistant for India

> "Just A Rather Very Intelligent System" — Built to be **private**, **blazing fast**, and **actually useful** for daily Indian life.

![JARVIS Banner](https://via.placeholder.com/800x200/0A2540/00FFAA?text=JARVIS+for+India) <!-- Replace with your own banner image later -->

**JARVIS** is a **fully local**, privacy-first AI assistant that runs entirely on your Windows PC (Linux & Mac support coming soon).  
No cloud services. No data leaks. No subscriptions.

It feels like Tony Stark’s JARVIS — natural, witty, and proactive — while staying extremely fast and lightweight on mid-range laptops.

### ✨ Key Highlights
- ⚡ **Blazing Fast** — Replies in **under 1 second** on local Ollama (llama3.2)
- 🧠 **Smart Memory System** — Short-term continuity + intelligent persistent memory with auto-promotion & deduplication
- 🎙️ **Voice-First Design** — Natural voice output (Edge TTS) + voice input in progress
- 🇮🇳 **Made for India** — IRCTC booking, Hyderabad defaults, Hinglish support planned
- 🔧 **Highly Modular** — Easy to extend with new skills
- 🔒 **100% Local & Private** — Powered by Ollama + local tools only

### Current Features
- Natural multi-turn conversations with strong short-term memory
- Hybrid Router (fast keyword shortcuts + intelligent LLM fallback)
- Voice output (easily toggleable)
- Web search via DuckDuckGo (with search bangs)
- Browser automation using Playwright (YouTube, IRCTC pages, etc.)
- Open apps, weather, date/time, and basic productivity skills
- 3 Personalities: Normal / Iron Man / Funny
- Experiential learning (JARVIS-CORE) through `train.py`
- **Optimized Memory System** with `core.py` + `promoter.py` + layered JSONL files

### Project Structure

```text
jarvis/
├── memory/                 # ← The Brain
│   ├── core.py             # Store, recall, scoring, conversation buffer
│   ├── promoter.py         # Auto-promotion, deduplication, archiving
│   ├── user_profile.json   # Permanent facts & preferences
│   ├── memory.jsonl        # Main capped conversation logs
│   ├── recent_memories.jsonl
│   ├── memory_archive.jsonl
│   └── experiences.json    # Curated technical knowledge
├── skills/                 # All capabilities
│   ├── router.py           # Hybrid intent router (fast + smart)
│   ├── browser.py
│   ├── web_search.py
│   └── ...
├── jarvis.py               # Main entry point
├── voice.py                # Voice input & output
├── train.py                # Experiential learning & training data
├── Modelfile               # Custom Ollama model
├── requirements.txt
└── README.md

### Quick Start

#### Requirements
- Windows 10/11
- Python 3.11+
- 8GB RAM (16GB recommended for smoother experience)
- [Ollama](https://ollama.com/download) installed

#### Installation

```bash
# Clone the repo
git clone https://github.com/2505a21058-jpg/-jarvis.git
cd -jarvis   # or rename folder to jarvis if you prefer

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install firefox

# Pull the local model
ollama pull llama3.2

# Run JARVIS
python jarvis.py