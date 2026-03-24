# JARVIS — Open Source AI Assistant for India

> "Just A Rather Very Intelligent System" — but make it Indian, private, and actually useful.

JARVIS is a free, open source, privacy-first AI assistant that runs 100% on your PC. No subscriptions, no cloud, no data harvesting. It actually **does things** — opens apps, searches the web, books train tickets, and learns from experience.

## Demo



> Voice command → real action. No babysitting required.

## What JARVIS can do right now

- **Voice + Text** — Talk or type, JARVIS responds with Christopher Neural voice
- **3 Personalities** — Normal, Iron Man JARVIS, and Funny (meme-aware)
- **Web Search** — DuckDuckGo with 13,000+ bangs (!yt, !amz, !gh, !reddit)
- **Open Apps** — Chrome, Calculator, Notepad, File Explorer by voice
- **Weather** — Real time weather for any city
- **Browser Automation** — Opens YouTube, Reddit, Amazon, IRCTC by voice
- **JARVIS-CORE** — Unique experiential learning model trained on real dev problems
- **100% Local** — Runs on Ollama + llama3.2, zero cloud dependency

## Coming Soon

- IRCTC ticket booking end to end
- Zomato/Swiggy food ordering
- Persistent memory (remembers you forever)
- Hindi/Hinglish support
- Web UI (chat in browser)
- Plugin marketplace
- Mobile app

## Quick Start

### Requirements
- Windows 10/11 (Linux/Mac support coming)
- Python 3.11
- 8GB RAM minimum (16GB recommended)
- [Ollama](https://ollama.com/download)

### Installation
```bash
git clone https://github.com/2505a21058-jpg/-jarvis.git
cd jarvis
py -3.11 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install firefox
ollama pull llama3.2
python jarvis.py
```

### First Run
1. Choose your personality (Normal / JARVIS / Funny)
2. Wait for "JARVIS Online"
3. Start talking or typing!

## Architecture
```
jarvis/
├── jarvis.py          # Master entry point
├── main.py            # AI brain + personalities  
├── voice.py           # Voice input/output
├── skills/            # Modular skill plugins
│   ├── router.py      # Intent routing
│   ├── web_search.py  # Wikipedia + weather
│   ├── browser.py     # Playwright automation
│   ├── open_app.py    # App launcher
│   └── datetime_skill.py
├── memory/            # JARVIS-CORE experiential learning
│   ├── experiences.json
│   └── training_data.jsonl
└── Modelfile          # Custom Ollama model definition
```

## Why JARVIS?

| Feature | Siri/Alexa | ChatGPT | Other Jarvis clones | This JARVIS |
|---|---|---|---|---|
| 100% Local | ❌ | ❌ | Partial | ✅ |
| India focused | ❌ | ❌ | ❌ | ✅ |
| Actually books tickets | ❌ | ❌ | ❌ | ✅ (coming) |
| Free forever | ❌ | ❌ | ✅ | ✅ |
| Experiential learning | ❌ | ❌ | ❌ | ✅ |
| Open source | ❌ | ❌ | ✅ | ✅ |

## Built With

- [Ollama](https://ollama.com) — Local AI inference
- [llama3.2](https://ollama.com/library/llama3.2) — AI model
- [Edge TTS](https://github.com/rany2/edge-tts) — Christopher Neural voice
- [Playwright](https://playwright.dev) — Browser automation
- [DuckDuckGo Bangs](https://duckduckgo.com/bangs) — Privacy-first search

## Contributing

PRs welcome! Especially for:
- India-specific skills (UPI, Aadhaar, DigiLocker)
- Hindi/regional language support
- New app integrations
- Bug fixes on Linux/Mac

## Roadmap

- [x] Phase 1 — Core AI + personalities
- [x] Phase 2 — Voice (Christopher Neural)
- [x] Phase 3 — Skills (search, weather, apps, browser)
- [ ] Phase 4 — Persistent memory (ChromaDB)
- [ ] Phase 5 — Web UI
- [ ] Phase 6 — IRCTC full booking
- [ ] Phase 7 — Hindi support
- [ ] Phase 8 — Plugin marketplace

## License

MIT — free forever, fork it, build on it, make it yours.

---

Built in Hyderabad 🇮🇳 | Star ⭐ if you find it useful!
```

Wait for autosave then push to GitHub:
```
git add .
git commit -m "Add README, LICENSE, requirements.txt"
git push