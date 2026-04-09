# JARVIS

Jarvis is a local AI assistant built as a structured runtime, not a simple chatbot. It combines deterministic command parsing, context-aware execution, multi-intent handling, and hybrid routing with local LLM fallback.

## Overview

Jarvis is designed around a parser-first architecture:
- commands are handled deterministically before any model call
- session context tracks the active app for follow-up actions
- the router decides when to execute skills directly and when to fall back to LLM reasoning
- local models run through Ollama for classification and response generation

This keeps common actions fast and predictable while still allowing conversational fallback when the query is not an actionable command.

## Architecture

High-level flow:

`User Input`
`-> Parser` (`skills/parser.py`)
`-> Context Layer` (`memory/context.py`)
`-> Router` (`skills/router.py`)
`-> Execution Engine` (`skills/` + `execution_engine.py`)
`-> LLM fallback`

Key ideas:
- Parser-first design: Jarvis tries deterministic command extraction before anything else.
- Context-aware execution: searches can reuse the last active app or site context.
- Classifier only when needed: the Gemma classifier runs only when the parser finds no commands.
- Execution stays local: app launches, browser actions, and command execution do not require an LLM.

## Features

- Deterministic command parser with support for both implicit and explicit multi-intent inputs
- Context-aware execution, such as searching YouTube after opening YouTube
- Multi-intent command handling with preserved action order
- Hybrid routing that combines parser rules, lightweight classification, and LLM fallback
- Local execution engine for launching apps and running system commands safely
- Local LLM support via Ollama for routing, summarization, and response generation

## Example Usage

```text
open chrome search news
-> opens Chrome
-> searches news using the active browser context

open youtube and search songs
-> opens YouTube
-> searches songs on YouTube using session context

play music
-> opens or routes to music playback flow directly
```

## Project Structure

```text
jarvis.py
skills/
  parser.py
  router.py
  classifier.py
  open_app.py
  browser.py
  search_engine.py
  weather.py
  train.py
memory/
  context.py
  core.py
execution_engine.py
model_manager.py
```

## Tech Stack

- Python
- Ollama for local model serving
- Gemma 1B for lightweight routing classification
- Llama and Qwen models for assistant responses
- Playwright for browser-driven flows where needed
- SQLite and JSON-based local storage for memory and fast recall

## Setup

```bash
git clone https://github.com/2505a21058-jpg/-jarvis.git
cd -jarvis
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install firefox
python jarvis.py
```

## Current Status

Core architecture is largely in place, around 85-90% complete for the current design.

Implemented:
- parser-driven command execution
- context-aware search and app flow
- local execution engine
- hybrid router with parser plus classifier plus LLM fallback
- local memory and response models

Next steps:
- richer agent-style execution planning
- more advanced long-term memory and retrieval
- broader skill coverage and deeper tool integration
