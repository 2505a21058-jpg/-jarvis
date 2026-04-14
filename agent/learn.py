from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


EXPERIENCES_PATH = Path("memory") / "experiences.jsonl"


def learn(
    observation: dict[str, Any],
    decision: dict[str, Any],
    result: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    experience = {
        "input": observation.get("input"),
        "decision": decision,
        "result": result,
        "evaluation": evaluation,
        "timestamp": datetime.now().isoformat(),
    }

    EXPERIENCES_PATH.parent.mkdir(exist_ok=True)
    with open(EXPERIENCES_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(experience, ensure_ascii=True) + "\n")

    return experience
