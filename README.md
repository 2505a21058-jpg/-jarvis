# RawVision for Jarvis

RawVision is a local-first perception and computer-control stack for desktop AI
agents. It reads semantic UI state from the operating system, browser engines,
framebuffer diffs, OCR, and screenshot fallbacks, then routes actions through
the safest available control engine.

The package is designed for Windows-first computer use, with graceful fallback
behavior when optional capture backends are unavailable.

## Quick Start

```bash
python -m pip install rawvision
```

For local development from this repository:

```bash
python -m pip install -e ".[windows,hands,ocr,dev]"
pytest tests/ -q
```

Minimal use:

```python
from rawvision import RawVision

ctx = RawVision().capture()
print(ctx.summary)
```

Recommended use:

```python
from rawvision import RawVision

vision = RawVision()
screen = vision.capture()
print(screen.to_llm())
```

One-shot helper:

```python
import rawvision

screen = rawvision.capture()
```

## Perception Stack

RawVision.capture() returns a `ScreenContext` built from multiple layers:

| Layer | Module | Purpose |
| --- | --- | --- |
| 0 | `rawvision.capture.process_monitor` | Foreground app metadata and app type |
| 1 | `rawvision.capture.uia_capture` | Windows UI Automation tree |
| 2 | `rawvision.capture.dom_capture` | Chrome/Electron CDP accessibility tree |
| 3 | `rawvision.capture.pixel_diff` | Changed framebuffer regions |
| 4 | `rawvision.capture.cv_capture` | OCR and lightweight CV on changed regions |
| 5 | `rawvision.capture.screenshot_capture` | Base64 PNG fallback for vision models |

Fusion modules score, deduplicate, and format results:

- `rawvision.fusion.arbitrator`
- `rawvision.fusion.deduplicator`
- `rawvision.fusion.formatter`

## Hands Stack

The Hands controller routes actions to the best engine:

| Engine | Module | Use |
| --- | --- | --- |
| CDP | `agent.hands.engines.cdp_engine` | Browser and Electron DOM actions |
| UIA | `agent.hands.engines.uia_engine` | Native semantic invoke/set-value |
| WinAPI | `agent.hands.engines.winapi_engine` | Win32 message actions |
| Terminal | `agent.hands.engines.terminal_engine` | Shell command execution |
| SendInput | `agent.hands.engines.sendinput_engine` | DPI-corrected fallback input |

```python
from agent.hands import HandsController

hands = HandsController()
```

## Computer Use Loop

`agent.computer_use.ComputerUseAgent` combines RawVision, Hands, and a local
vision planner such as LLaVA or Moondream through Ollama.

```python
from agent.computer_use import ComputerUseAgent

agent = ComputerUseAgent(max_steps=8)
result = agent.run("open the Save dialog and confirm")
print(result.final_reason)
```

Set the local vision model with:

```bash
set JARVIS_VISION_MODEL=llava
```

or:

```bash
set JARVIS_VISION_MODEL=moondream
```

## Optional Dependencies

Install only what you need:

```bash
python -m pip install "rawvision[windows]"
python -m pip install "rawvision[hands]"
python -m pip install "rawvision[ocr]"
```

Full local development:

```bash
python -m pip install -e ".[windows,hands,ocr,dev]"
```

## Running Tests

```bash
pytest tests/ -q
```

Focused RawVision and Hands tests:

```bash
powershell -Command "$files = @(Get-ChildItem tests\test_rawvision_*.py) + @(Get-ChildItem tests\test_hands_*.py); pytest @($files.FullName) -q"
```

## Public API

```python
from rawvision import RawVision, ScreenContext

screen: ScreenContext = RawVision().capture()
```

The package also exports:

- `UIElement`
- `BoundingBox`
- `ElementRole`
- `ElementSource`
- `CaptureLayer`
- `LayerResult`

## Notes

- UIA, WinAPI, and SendInput paths are Windows-specific.
- CDP capture requires Chrome or Electron to expose a debug port.
- OCR engines are optional and loaded lazily.
- Missing optional backends fail gracefully as failed `LayerResult`s.

## License

MIT
