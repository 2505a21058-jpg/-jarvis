"""
agent/harness/
Browser harness - persistent CDP connection to Chrome and Electron apps.
"""

from .browser import BrowserHarness, get_harness
from .tab import Tab

__all__ = ["BrowserHarness", "get_harness", "Tab"]
