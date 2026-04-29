from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
import time


@dataclass
class SkillResult:
    success: bool
    output: Any
    error: Optional[str] = None
    duration_ms: float = 0.0
    skill_name: str = ""


class SkillBase(ABC):
    name: str = ""
    description: str = ""
    timeout_seconds: float = 10.0

    @abstractmethod
    def execute(self, params: dict, state: Any) -> SkillResult:
        pass

    def run(self, params: dict, state: Any) -> SkillResult:
        start = time.monotonic()
        try:
            result = self.execute(params, state)
        except TimeoutError:
            result = SkillResult(success=False, output=None, error="Timeout", skill_name=self.name)
        except Exception as e:
            result = SkillResult(success=False, output=None, error=str(e), skill_name=self.name)
        result.duration_ms = (time.monotonic() - start) * 1000
        result.skill_name = self.name
        return result
