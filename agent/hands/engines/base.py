"""Shared result type for Hands engines."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionResult:
    success: bool
    message: str = ""
    engine: str = ""
    data: dict = field(default_factory=dict)


def ok(engine: str, message: str = "", **data) -> ActionResult:
    return ActionResult(success=True, message=message, engine=engine, data=data)


def fail(engine: str, message: str = "", **data) -> ActionResult:
    return ActionResult(success=False, message=message, engine=engine, data=data)
