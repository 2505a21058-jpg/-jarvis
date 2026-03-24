import json
import os

experiences = [
    {
        "id": "exp_001",
        "problem": "pyaudio blocks terminal on Windows",
        "patterns": ["blocking I/O", "Windows signal handling", "C extension"],
        "context": {"os": "Windows 11", "python": "3.11"},
        "failed_attempts": [
            {"approach": "exception_on_overflow=False", "why": "still blocks at C level"},
            {"approach": "threading.Event", "why": "signal not delivered during native call"}
        ],
        "solution": "callback mode with time.sleep in main thread",
        "principle": "Never block main thread with native I/O calls on Windows. Use async callback pattern instead."
    },
    {
        "id": "exp_002",
        "problem": "VS Code not saving files to subfolders",
        "patterns": ["file locking", "editor interference", "silent failure"],
        "context": {"os": "Windows 11", "editor": "VS Code"},
        "failed_attempts": [
            {"approach": "Ctrl+S in VS Code", "why": "file locked by editor process"},
            {"approach": "setup.py write", "why": "setup.py had old code cached"}
        ],
        "solution": "write files directly using terminal python -c one-liners",
        "principle": "When editor silently fails to save, bypass it entirely with direct terminal file writes."
    },
    {
        "id": "exp_003",
        "problem": "tflite runtime incompatible with Python 3.11 on Windows",
        "patterns": ["version incompatibility", "platform limitation", "dependency chain"],
        "context": {"os": "Windows 11", "python": "3.11"},
        "failed_attempts": [
            {"approach": "pip install tflite-runtime", "why": "no Windows 3.11 wheel exists"},
            {"approach": "pip install tensorflow", "why": "installs but tflite models still fail"}
        ],
        "solution": "use onnxruntime as alternative or wait for Phase 6 Web UI approach",
        "principle": "When a library has platform gaps, find an alternative runtime or redesign the feature for a different layer."
    },
    {
        "id": "exp_004",
        "problem": "DuckDuckGo blocks Python requests scraper",
        "patterns": ["bot detection", "scraping blocked", "HTTP 403"],
        "context": {"library": "requests", "target": "duckduckgo.com/html"},
        "failed_attempts": [
            {"approach": "requests.get with default headers", "why": "detected as bot"},
            {"approach": "custom User-Agent", "why": "DuckDuckGo HTML still blocks"}
        ],
        "solution": "use official API endpoint or Wikipedia REST API",
        "principle": "When a website blocks scraping, always check for an official API endpoint first."
    },
    {
        "id": "exp_005",
        "problem": "edge-tts slow with multiple sentence requests",
        "patterns": ["network latency", "sequential requests", "TTS lag"],
        "context": {"library": "edge-tts"},
        "failed_attempts": [
            {"approach": "split into sentences and speak each", "why": "N network requests = N seconds lag"},
            {"approach": "parallel asyncio.gather", "why": "better but still multiple requests"}
        ],
        "solution": "send entire response as single TTS request",
        "principle": "Minimize network round trips. One large request is always faster than many small ones."
    },
    {
        "id": "exp_006",
        "problem": "Chrome not opening when already running",
        "patterns": ["singleton process", "existing instance", "subprocess"],
        "context": {"app": "Google Chrome", "library": "subprocess"},
        "failed_attempts": [
            {"approach": "subprocess.Popen(chrome_path)", "why": "passes args to existing instance silently"}
        ],
        "solution": "add --new-window flag to force new window",
        "principle": "Some apps are singletons. Always include flags that force new window behavior."
    },
    {
        "id": "exp_007",
        "problem": "URL ampersands break Windows CMD terminal",
        "patterns": ["shell escaping", "special characters", "Windows CMD"],
        "context": {"os": "Windows", "shell": "cmd.exe"},
        "failed_attempts": [
            {"approach": "paste URL with & in python -c command", "why": "& splits command at shell level"}
        ],
        "solution": "use string concatenation instead of f-strings with URLs",
        "principle": "In Windows CMD, & is a command separator. Use variable concatenation for URLs."
    },
    {
        "id": "exp_008",
        "problem": "Wikipedia API returns 403 without User-Agent",
        "patterns": ["API authentication", "missing headers", "HTTP 403"],
        "context": {"api": "Wikipedia REST API"},
        "failed_attempts": [
            {"approach": "requests.get with no headers", "why": "Wikipedia requires User-Agent header"}
        ],
        "solution": "add User-Agent header identifying the project",
        "principle": "When getting 403, always try adding a descriptive User-Agent header first."
    }
]

os.makedirs('memory', exist_ok=True)

with open('memory/experiences.json', 'w') as f:
    json.dump(experiences, f, indent=2)

print(f"Saved {len(experiences)} experiences!")

training_data = []

for exp in experiences:
    training_data.append({
        "prompt": f"I am facing this problem: {exp['problem']}. Context: {exp['context']}. What should I do?",
        "response": f"Based on similar experience: {exp['solution']}. The key principle: {exp['principle']}"
    })
    training_data.append({
        "prompt": f"I see these patterns: {', '.join(exp['patterns'])}. What kind of issue is this?",
        "response": f"These patterns suggest: {exp['problem']}. {exp['principle']}"
    })
    for attempt in exp['failed_attempts']:
        training_data.append({
            "prompt": f"I tried {attempt['approach']} but it failed. Why?",
            "response": f"That fails because: {attempt['why']}. Instead try: {exp['solution']}. Remember: {exp['principle']}"
        })

with open('memory/training_data.jsonl', 'w') as f:
    for item in training_data:
        f.write(json.dumps(item) + '\n')

print(f"Created {len(training_data)} training examples!")
print("\nSample:")
print(json.dumps(training_data[0], indent=2))
