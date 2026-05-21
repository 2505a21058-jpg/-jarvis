"""
agent/hands/
Jarvis Hands - zero-simulation app control.
Routes actions to the right engine based on app type.
"""

from .controller import HandsController, get_hands
from .engines import ActionResult
from .router import ActionRouter, AppClassifier

__all__ = [
    "HandsController",
    "get_hands",
    "ActionResult",
    "AppClassifier",
    "ActionRouter",
]
