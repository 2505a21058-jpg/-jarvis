"""
skills/automation/hero/setup.py

Hero (Ulixee) setup and connection manager.
Hero runs as a Node.js service.
Python connects via HTTP to the Hero Core server.

Setup (run once):
    node --version  (needs Node 16+)
    npm install -g @ulixee/hero-core @ulixee/hero

Then start the Hero server:
    npx @ulixee/hero-core &

Or Jarvis starts it automatically.
"""

from __future__ import annotations
import json
import logging
import os
import subprocess
import time
import urllib.request
from typing import Optional

logger = logging.getLogger("jarvis.hero")

_HERO_PORT    = int(os.getenv("JARVIS_HERO_PORT", "1818"))
_HERO_BASE    = f"http://localhost:{_HERO_PORT}"

# Search order for Node.js executable:
# 1. JARVIS_NODE env var
# 2. Playwright-bundled node.exe
# 3. System PATH (node)
# 4. Common install locations
_PLAYWRIGHT_NODE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "venv", "Lib", "site-packages", "playwright", "driver", "node.exe"
)

def _find_node() -> Optional[str]:
    """Find a usable Node.js executable."""
    env_node = os.getenv("JARVIS_NODE")
    if env_node and os.path.isfile(env_node):
        return env_node
    if os.path.isfile(_PLAYWRIGHT_NODE):
        return os.path.abspath(_PLAYWRIGHT_NODE)
    common = [
        "C:\\tools\\nodejs\\node.exe",
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "nodejs", "node.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "nodejs", "node.exe"),
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "fnm", "aliases", "default", "node.exe"),
    ]
    for path in common:
        if os.path.isfile(path):
            return path
    return None

def _node_dir() -> Optional[str]:
    node = _find_node()
    return os.path.dirname(node) if node else None

# Search order for @ulixee/hero-core:
# 1. JARVIS_HERO_MODULES env var
# 2. npm global root
# 3. $USERPROFILE/node_modules (npm installs here when not on PATH)
# 4. Old %APPDATA%/npm/node_modules location
def _find_hero_core() -> Optional[str]:
    env_path = os.getenv("JARVIS_HERO_MODULES")
    if env_path:
        candidate = os.path.join(env_path, "@ulixee", "hero-core", "index.js")
        if os.path.isfile(candidate):
            return candidate
    search_roots = []
    node = _find_node()
    if node:
        # npm root -g relative to the node we found
        npm_root = os.path.join(os.path.dirname(node), "node_modules")
        search_roots.append(npm_root)
    search_roots.extend([
        os.path.join(os.path.expanduser("~"), "node_modules"),
        os.path.join(os.environ.get("APPDATA", ""), "npm", "node_modules"),
    ])
    for root in search_roots:
        candidate = os.path.join(root, "@ulixee", "hero-core", "index.js")
        if os.path.isfile(candidate):
            return candidate
    return None

_hero_process: Optional[subprocess.Popen] = None


def is_hero_available() -> bool:
    """Check if Hero Core server is running."""
    try:
        with urllib.request.urlopen(
            f"{_HERO_BASE}/", timeout=2
        ) as resp:
            return resp.status in (200, 404)
    except Exception:
        return False


def _get_node_version(node_path: str) -> str:
    try:
        result = subprocess.run(
            [node_path, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "?"
    except Exception:
        return "?"


def ensure_hero_running() -> bool:
    """
    Start Hero Core if not running.
    Returns True if Hero is available.
    """
    global _hero_process

    if is_hero_available():
        logger.info("[HERO] Already running on port %s", _HERO_PORT)
        return True

    node_path = _find_node()
    if not node_path:
        logger.warning(
            "[HERO] Node.js not found. "
            "Install Node.js from https://nodejs.org or check your PATH."
        )
        return False

    node_dir = os.path.dirname(node_path)
    node_version = _get_node_version(node_path)
    logger.info("[HERO] Node.js: %s (%s)", node_version or "?", node_path)

    hero_core_path = _find_hero_core()
    if not hero_core_path:
        logger.warning(
            "[HERO] @ulixee/hero-core not found. "
            "Run the following to install:\n"
            "  npm install -g @ulixee/hero-core @ulixee/hero\n"
            "Hero features will be unavailable."
        )
        return False

    # Start Hero Core, adding node_dir to PATH so native modules work
    try:
        env = dict(os.environ)
        env["PATH"] = f"{node_dir}{os.pathsep}{env.get('PATH', '')}"

        _hero_process = subprocess.Popen(
            [node_path, hero_core_path, "--port", str(_HERO_PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )

        # Wait for startup
        for _ in range(20):
            if is_hero_available():
                logger.info("[HERO] Started on port %s", _HERO_PORT)
                return True
            time.sleep(0.5)

        logger.warning("[HERO] Started but not responding")
        return False

    except Exception as e:
        logger.error("[HERO] Start failed: %s", e)
        return False


def stop_hero():
    """Stop Hero Core process."""
    global _hero_process
    if _hero_process:
        _hero_process.terminate()
        _hero_process = None
        logger.info("[HERO] Stopped")
