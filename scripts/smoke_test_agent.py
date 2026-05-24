"""
Smoke test for the AgentSkill ReAct loop against a real Ollama model.
Run: python scripts/smoke_test_agent.py
"""

import sys
import time
from pathlib import Path

# Ensure project root is on sys.path so absolute imports like "models.llm" work
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


PASS = 0
FAIL = 0


def report(step: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    tail = f" -- {detail}" if detail else ""
    print(f"  [{status}] {step}{tail}")
    return ok


def heading(n: int, text: str):
    print(f"\n=== Step {n}: {text} ===")


# ---------------------------------------------------------------------------
# Step 1: Basic LLM call
# ---------------------------------------------------------------------------
heading(1, "Basic LLM call")

from models.llm import call_llm_tools

response = call_llm_tools(
    messages=[{"role": "user", "content": "Say hello in exactly 5 words."}],
    temperature=0.0,
    max_tokens=50,
    timeout=30,
    retries=0,
)
content = response.get("content", "")
report("LLM returned text content", bool(content), repr(content[:80]))

# ---------------------------------------------------------------------------
# Step 2: Tool calling
# ---------------------------------------------------------------------------
heading(2, "Tool calling")

response = call_llm_tools(
    messages=[{"role": "user", "content": "Search for 'python testing framework'"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }],
    temperature=0.0,
    max_tokens=512,
    timeout=30,
    retries=0,
)

tool_calls = response.get("tool_calls")
if tool_calls and len(tool_calls) > 0:
    fn = tool_calls[0].get("function", {}) if isinstance(tool_calls[0], dict) else tool_calls[0].function
    name = fn.get("name", "") if isinstance(fn, dict) else fn.name
    args = fn.get("arguments", "") if isinstance(fn, dict) else fn.arguments
    report("LLM chose a tool", True, f"{name}({args})")
else:
    report("LLM chose a tool", False, f"No tool_calls in response: content={repr(content)}")

# ---------------------------------------------------------------------------
# Step 3: AgentSkill.execute() with hello-agent manifest
# ---------------------------------------------------------------------------
heading(3, "AgentSkill full execution")

from skills.catalog import SkillCatalog

catalog = SkillCatalog(Path("skills/catalog"))
manifests = catalog.discover()
skill = catalog.load_skills().get("hello_agent")

if not skill:
    report("hello_agent found in catalog", False)
    sys.exit(1)

report("hello_agent loaded from catalog", True, skill.__class__.__name__)

# Patch out browser-dependent tools: override STEP_FUNCS to prevent real browser launch
import json
from unittest.mock import patch
from skills.app_helpers import STEP_FUNCS

# Create safe stubs for browser tools
_safe_funcs = {k: lambda p, ctx: True for k in STEP_FUNCS}

with patch("skills.app_helpers.STEP_FUNCS", _safe_funcs):
    result = skill.execute(
        {"query": "Search for the Python programming language and tell me what it is."},
        None,
    )

report("AgentSkill execute succeeded", result.success, repr(result.output[:120]))
assert result.success, f"Execution failed: {result.error}"
assert len(result.output) > 20, f"Output too short: {repr(result.output)}"

# ---------------------------------------------------------------------------
# Step 4: Multi-turn ReAct loop
# ---------------------------------------------------------------------------
heading(4, "Multi-turn ReAct loop")

# Create an agent skill that must use at least 2 tool calls to answer
from skills.manifest import SkillManifest
from skills.catalog import AgentSkill

manifest = SkillManifest(
    name="research-agent",
    description="Research agent that searches and analyzes",
    instructions="Search for the topic, then analyze the results using a second LLM call.",
    steps=[],
)

agent = AgentSkill(manifest)

with patch("skills.app_helpers.STEP_FUNCS", _safe_funcs):
    result = agent.execute(
        {"query": "What is the capital of France? First search for it, then verify."},
        None,
    )

report("Multi-turn succeeded", result.success, repr(result.output[:120]))
assert result.success, f"Multi-turn failed: {result.error}"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
print(f"  {PASS} passed, {FAIL} failed")
if FAIL == 0:
    print("  All smoke tests PASSED")
else:
    print("  SOME TESTS FAILED")
    sys.exit(1)
