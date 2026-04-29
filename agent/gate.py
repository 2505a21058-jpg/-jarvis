"""
agent/gate.py

Tier 1 routing: deterministic, zero-LLM resolution of common inputs.
Any input resolved here bypasses decide(), plan(), and the LLM entirely.
Target: resolve >60% of common commands with <2ms latency.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional


logger = logging.getLogger("jarvis.gate")


def _extract_reminder_params(match: re.Match) -> dict:
    groups = match.groupdict()
    message = (groups.get("message") or "Check in").strip()
    delay = (groups.get("delay") or "1 minute").strip()
    return {"message": message, "delay": delay}


def _monitor_params(metric: str, match: re.Match) -> dict:
    threshold = 80.0
    if "threshold" in match.groupdict() and match.group("threshold"):
        threshold = float(match.group("threshold"))
    return {"action": "monitor", "metric": metric, "threshold": threshold}


def _stop_monitor_params(match: re.Match) -> dict:
    metric = match.group("metric").strip().lower()
    if metric == "memory":
        metric = "ram"
    return {"action": "stop", "metric": metric}


@dataclass
class GateDecision:
    resolved: bool
    skill_name: str = ""
    params: dict = field(default_factory=dict)
    direct_response: str = ""
    confidence: float = 1.0
    rule_id: str = ""


class GateRule:
    """A single deterministic routing rule."""

    def __init__(
        self,
        rule_id: str,
        patterns: list[str],
        skill_name: str,
        param_extractor: Callable[[re.Match], dict],
        description: str = "",
    ):
        self.rule_id = rule_id
        self.compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        self.skill_name = skill_name
        self.param_extractor = param_extractor
        self.description = description

    def match(self, text: str) -> Optional[GateDecision]:
        for pattern in self.compiled:
            match = pattern.fullmatch(text.strip())
            if not match:
                continue
            try:
                params = self.param_extractor(match)
            except Exception as exc:
                logger.warning("Rule %s param_extractor failed: %s", self.rule_id, exc)
                return None
            logger.debug("Gate rule matched: %s", self.rule_id)
            direct_response = str(params.get("response", "")).strip() if self.skill_name == "__direct_response__" else ""
            return GateDecision(
                resolved=True,
                skill_name=self.skill_name,
                params=params,
                direct_response=direct_response,
                confidence=1.0,
                rule_id=self.rule_id,
            )
        return None


GATE_RULES: list[GateRule] = [
    GateRule(
        rule_id="browse_url",
        patterns=[
            r"(?:go to|open|visit|browse to?)\s+(?P<url>https?://\S+)",
            r"(?P<url>https?://\S+)",
        ],
        skill_name="browse",
        param_extractor=lambda match: {"url": match.group("url").strip()},
        description="Navigate to a URL",
    ),
    GateRule(
        rule_id="read_report",
        patterns=[
            r"read(?: the)? (?:report|file|pdf|document)\s+(?P<path>\S+)",
            r"summarize\s+(?P<path>\S+)",
            r"open(?: and read)? (?P<path>\S+\.(?:pdf|txt|md|csv))",
        ],
        skill_name="read_report",
        param_extractor=lambda match: {"path": match.group("path").strip()},
        description="Read and summarize a file",
    ),
    GateRule(
        rule_id="launch_claude_code",
        patterns=[
            r"open(?: cursor| claude code| vscode| vs code)(?:\s+at\s+(?P<path>\S+))?",
            r"launch(?: cursor| claude code)(?:\s+at\s+(?P<path>\S+))?",
            r"start cursor(?:\s+at\s+(?P<path>\S+))?",
        ],
        skill_name="launch_claude_code",
        param_extractor=lambda match: {
            "path": (
                match.group("path")
                if "path" in match.groupdict() and match.group("path")
                else "."
            ).strip()
        },
        description="Open Cursor or Claude Code editor",
    ),
    GateRule(
        rule_id="system_search_folder",
        patterns=[
            r"(?:is there|find|search for|look for|check (?:if|for)) (?:a )?folder (?:named |called )?(?P<query>.+?)(?:\s+on my (?:pc|computer|device|system))?",
            r"(?:find|search for) (?:a )?folder (?P<query>.+)",
            r"do i have (?:a )?folder (?:called |named )?(?P<query>.+)",
        ],
        skill_name="system_search",
        param_extractor=lambda match: {"query": match.group("query").strip(), "search_type": "folder"},
        description="Search for a folder on the local filesystem",
    ),
    GateRule(
        rule_id="system_search_file",
        patterns=[
            r"(?:find|search for|look for) (?:a )?file (?:named |called )?(?P<query>.+?)(?:\s+on my (?:pc|computer|device|system))?",
            r"(?:is there|do i have) (?:a )?file (?:called |named )?(?P<query>.+)",
        ],
        skill_name="system_search",
        param_extractor=lambda match: {"query": match.group("query").strip(), "search_type": "file"},
        description="Search for a file on the local filesystem",
    ),
    GateRule(
        rule_id="open_app",
        patterns=[
            r"open\s+(?P<app>\w[\w\s]*)",
            r"launch\s+(?P<app>\w[\w\s]*)",
            r"start\s+(?P<app>\w[\w\s]*)",
        ],
        skill_name="open_app",
        param_extractor=lambda match: {"app": match.group("app").strip().lower()},
        description="Open / launch an application",
    ),
    GateRule(
        rule_id="type_text",
        patterns=[
            r"type\s+(?P<text>.+)",
            r"type this[:\s]+(?P<text>.+)",
            r"write\s+(?P<text>.+)",
        ],
        skill_name="type_text",
        param_extractor=lambda match: {"text": match.group("text").strip()},
        description="Type text via keyboard automation",
    ),
    GateRule(
        rule_id="system_status",
        patterns=[
            r"(?:show|what(?:'s| is)) (?:my )?(?:system|pc|computer) (?:status|stats|usage|performance)",
            r"how (?:much|is) (?:my )?(?:ram|cpu|memory|disk) (?:usage|used|doing)",
            r"(?:check|show) (?:ram|cpu|memory|disk)(?: usage)?",
        ],
        skill_name="system_monitor",
        param_extractor=lambda match: {"action": "status"},
        description="Show current system resource usage",
    ),
    GateRule(
        rule_id="monitor_ram",
        patterns=[
            r"(?:monitor|watch|track|alert me (?:if|when)) (?:my )?(?:ram|memory)(?: usage)?(?: (?:goes?|is) above (?P<threshold>\d+)%?)?",
            r"(?:keep track of|notify me about) (?:my )?(?:memory|ram)(?: (?:usage|if it goes above (?P<threshold>\d+)%?))?",
        ],
        skill_name="system_monitor",
        param_extractor=lambda match: _monitor_params("ram", match),
        description="Monitor RAM usage with optional threshold alert",
    ),
    GateRule(
        rule_id="monitor_cpu",
        patterns=[
            r"(?:monitor|watch|track|alert me (?:if|when)) (?:my )?cpu(?: usage)?(?: (?:goes?|is) above (?P<threshold>\d+)%?)?",
            r"(?:keep track of|notify me about) (?:my )?cpu(?: (?:usage|if it goes above (?P<threshold>\d+)%?))?",
        ],
        skill_name="system_monitor",
        param_extractor=lambda match: _monitor_params("cpu", match),
        description="Monitor CPU usage with optional threshold alert",
    ),
    GateRule(
        rule_id="monitor_disk",
        patterns=[
            r"(?:monitor|watch|track|alert me (?:if|when)) (?:my )?disk(?: usage)?(?: (?:goes?|is) above (?P<threshold>\d+)%?)?",
            r"(?:keep track of|notify me about) (?:my )?disk(?: (?:usage|if it goes above (?P<threshold>\d+)%?))?",
        ],
        skill_name="system_monitor",
        param_extractor=lambda match: _monitor_params("disk", match),
        description="Monitor disk usage with optional threshold alert",
    ),
    GateRule(
        rule_id="stop_monitoring",
        patterns=[
            r"stop monitoring (?P<metric>ram|memory|cpu|disk|all)",
            r"cancel (?P<metric>ram|memory|cpu|disk|all) monitoring",
        ],
        skill_name="system_monitor",
        param_extractor=_stop_monitor_params,
        description="Stop an active system monitor",
    ),
    GateRule(
        rule_id="set_reminder",
        patterns=[
            r"remind me (?:in )?(?P<delay>.+?) to (?P<message>.+)",
            r"set (?:a )?reminder (?:for )?(?P<delay>.+?) (?:to|about) (?P<message>.+)",
            r"(?:remind|alert|notify) me (?:about|to) (?P<message>.+?) in (?P<delay>.+)",
            r"remind me (?:in )?(?P<delay>\d+(?:\.\d+)?\s*(?:seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h))",
            r"set (?:a )?reminder (?:in|for) (?P<delay>\d+(?:\.\d+)?\s*(?:seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h))",
        ],
        skill_name="reminder",
        param_extractor=_extract_reminder_params,
        description="Set a timed reminder",
    ),
    GateRule(
        rule_id="search_web",
        patterns=[
            r"search(?: for| the web for)?\s+(?P<query>.+)",
            r"google\s+(?P<query>.+)",
            r"look up\s+(?P<query>.+)",
        ],
        skill_name="browse",
        param_extractor=lambda match: {"query": match.group("query").strip()},
        description="Web search",
    ),
    GateRule(
        rule_id="heartbeat_status",
        patterns=[
            r"(?:what are you|are you) (?:monitoring|watching|tracking)",
            r"any (?:updates|alerts|notifications)(?: for me)?",
            r"heartbeat status",
        ],
        skill_name="__direct_response__",
        param_extractor=lambda match: {
            "response": "I'm monitoring: recent memory patterns, pending tasks, "
            "and your Downloads folder. I'll notify you proactively "
            "when something needs your attention."
        },
        description="Explain heartbeat monitoring",
    ),
    GateRule(
        rule_id="list_skills",
        patterns=[
            r"(?:list|show|what are)(?: your)? skills?",
            r"what can you do",
            r"help",
        ],
        skill_name="list_skills",
        param_extractor=lambda match: {},
        description="List available skills",
    ),
    GateRule(
        rule_id="greet",
        patterns=[
            r"(?:hi|hello|hey|howdy|greetings)[\s!.]*",
            r"(?:hi|hello|hey)\s+jarvis[\s!.]*",
        ],
        skill_name="__direct_response__",
        param_extractor=lambda match: {"response": "Hello! How can I help you today?"},
        description="Simple greeting",
    ),
    GateRule(
        rule_id="thanks",
        patterns=[
            r"(?:thanks?|thank you|cheers|ty)[\s!.]*",
        ],
        skill_name="__direct_response__",
        param_extractor=lambda match: {"response": "You're welcome!"},
        description="Acknowledgement",
    ),
]


class GateLayer:
    """
    Evaluates all rules against user input.
    Returns first match or unresolved GateDecision.
    """

    def __init__(self, rules: list[GateRule] | None = None):
        self._rules = rules or GATE_RULES
        self._hit_count: dict[str, int] = {}
        self._miss_count: int = 0

    def evaluate(self, user_input: str) -> GateDecision:
        text = str(user_input or "").strip()
        for rule in self._rules:
            decision = rule.match(text)
            if decision:
                self._hit_count[rule.rule_id] = self._hit_count.get(rule.rule_id, 0) + 1
                return decision
        self._miss_count += 1
        return GateDecision(resolved=False)

    def add_rule(self, rule: GateRule) -> bool:
        existing_ids = {existing.rule_id for existing in self._rules}
        if rule.rule_id in existing_ids:
            logger.debug("Gate rule already exists, skipping: %s", rule.rule_id)
            return False
        self._rules.insert(0, rule)
        logger.info("Gate rule added dynamically: %s", rule.rule_id)
        return True

    def stats(self) -> dict:
        total = sum(self._hit_count.values()) + self._miss_count
        return {
            "total": total,
            "hits": sum(self._hit_count.values()),
            "misses": self._miss_count,
            "hit_rate": sum(self._hit_count.values()) / max(total, 1),
            "rule_hits": dict(self._hit_count),
        }


_gate_instance: Optional[GateLayer] = None


def get_gate() -> GateLayer:
    global _gate_instance
    if _gate_instance is None:
        _gate_instance = GateLayer()
    return _gate_instance
