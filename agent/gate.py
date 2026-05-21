"""
agent/gate.py - DEPRECATED

This module has been replaced by the intent classification system:
  agent/intent/classifier.py - unified intent classifier
  agent/intent/rules.py - rule-based classification
  agent/intent/router.py - intent to skill routing

Retained for reference. Not called from agent/loop.py.
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


def _set_env_params(match: re.Match) -> dict:
    groups = match.groupdict()
    var = (groups.get("var") or "").strip().upper()
    raw_val = groups.get("val")
    if raw_val:
        return {"var": var, "val": raw_val.strip().strip("\"'")}

    text = match.group(0).strip().lower()
    if text.startswith("disable") or "turn off" in text:
        return {"var": var, "val": "false"}
    return {"var": var, "val": "true"}


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
        rule_id="compose_email_browser",
        patterns=[
            r"(?:open\s+)?(?:gmail|mail|email)\s+and\s+(?:send|compose|write)\s+(?:a\s+)?(?:mail|email|message)\s+to\s+(?P<to>\S+@\S+)\s*(?:about|asking|saying|regarding|with subject|sending)?\s*(?P<body>.+)?",
            r"send\s+(?:gmail|mail|email|a mail|an email|a message)\s+to\s+(?P<to>\S+@\S+)\s*(?:sending|about|asking|saying|regarding|with message)?\s*(?P<body>.+)?",
            r"send\s+(?:an?\s+)?(?:email|mail|message)\s+to\s+(?P<to>\S+@\S+)\s+(?:about|asking|saying|regarding|sending|inviting|with)?\s*(?P<body>.+)?",
            r"email\s+(?P<to>\S+@\S+)\s+(?:about|asking|saying|and say|and ask|sending|inviting)?\s*(?P<body>.+)?",
            r"compose\s+(?:an?\s+)?(?:email|mail)\s+to\s+(?P<to>\S+@\S+)\s*(?P<body>.*)?",
            r"write\s+(?:an?\s+)?(?:email|mail|message)\s+to\s+(?P<to>\S+@\S+)\s*(?:about|saying|asking)?\s*(?P<body>.*)?",
            r"gmail\s+(?P<to>\S+@\S+)\s*(?P<body>.*)?",
        ],
        skill_name="compose_email",
        param_extractor=lambda match: {
            "to": match.group("to").strip(),
            "body": (
                match.group("body").strip()
                if "body" in match.groupdict() and match.group("body")
                else ""
            ),
        },
        description="Compose and send an email via browser or SMTP",
    ),
    GateRule(
        rule_id="open_and_type",
        patterns=[
            r"open\s+(?P<app>\w[\w\s]{0,20}?)\s+and\s+type\s+(?P<text>.+)",
            r"open\s+(?P<app>\w[\w\s]{0,20}?)\s+(?:and\s+)?(?:then\s+)?type\s+(?P<text>.+)",
            r"open\s+(?P<app>\w[\w\s]{0,20}?)\s+and\s+write\s+(?P<text>.+)",
        ],
        skill_name="open_and_type",
        param_extractor=lambda match: {
            "app": match.group("app").strip().lower(),
            "text": match.group("text").strip(),
        },
        description="Open an app then type text into it",
    ),
    GateRule(
        rule_id="open_search_and_play",
        patterns=[
            r"open\s+(?P<app>\w+)[,\s]+search\s+(?:for\s+)?(?P<query>.+?)\s+and\s+(?:play|watch|open|click|select)\s+(?:the\s+)?(?:first|top|best)\s+(?:result|video|song|one)",
            r"open\s+(?P<app>\w+)\s+search\s+(?:for\s+)?(?P<query>.+?)\s+and\s+(?:play|watch|open|click|select)\s+(?:the\s+)?(?:first|top|best)(?:\s+(?:result|video|song|one))?",
            r"open\s+(?P<app>\w+)[,\s]+(?:search|find)\s+(?P<query>.+?)\s+and\s+(?:play|watch|open)\s+(?:it|the\s+first\s+one)?",
        ],
        skill_name="open_search_and_play",
        param_extractor=lambda m: {
            "app": m.group("app").strip().lower(),
            "query": m.group("query").strip(),
        },
        description="Open app, search, and interact with first result",
    ),
    GateRule(
        rule_id="open_search_then_action",
        patterns=[
            r"open\s+(?P<app>\w+)[,\s]+search\s+(?:for\s+)?(?P<query>.+?)\s+and\s+(?P<action>download|share|like|subscribe|bookmark)\s+(?:the\s+)?(?:first|it|that)",
        ],
        skill_name="open_and_search",
        param_extractor=lambda m: {
            "app": m.group("app").strip().lower(),
            "query": m.group("query").strip(),
        },
        description="Open app and search (action on result noted but not executed)",
    ),
    GateRule(
        rule_id="open_and_search",
        patterns=[
            r"open\s+(?P<app>\w+)\s+and\s+search\s+(?:for\s+)?(?P<query>.+)",
            r"go to\s+(?P<app>\w+)\s+and\s+search\s+(?:for\s+)?(?P<query>.+)",
            r"open\s+(?P<app>\w+)\s+and\s+(?:look up|find)\s+(?P<query>.+)",
        ],
        skill_name="open_and_search",
        param_extractor=lambda match: {
            "app": match.group("app").strip().lower(),
            "query": match.group("query").strip(),
        },
        description="Open an app then search within it",
    ),
    GateRule(
        rule_id="open_and_browse",
        patterns=[
            r"open\s+(?P<app>\w+)\s+and\s+(?:go to|navigate to|open)\s+(?P<url>https?://\S+)",
            r"open\s+(?P<app>\w+)\s+then\s+(?:go to|browse to)\s+(?P<url>.+)",
        ],
        skill_name="open_and_browse",
        param_extractor=lambda match: {
            "app": match.group("app").strip().lower(),
            "url": match.group("url").strip(),
        },
        description="Open an app then navigate to a URL",
    ),
    GateRule(
        rule_id="computer_control",
        patterns=[
            r"(?:automate|control|use\s+(?:my\s+)?(?:computer|pc|device)\s+to)\s+(?P<task>.+)",
            r"(?P<task>draw\s+.+\s+(?:in|on)\s+(?:microsoft\s+)?paint.*)",
            r"(?P<task>open\s+.+\b(?:book|buy|purchase|pay|checkout|fill|submit|click|select|draw)\b.*)",
            r"(?P<task>(?:book|buy|purchase|reserve|order)\s+.+)",
            r"(?P<task>fill\s+(?:the\s+)?(?:form|fields?)\s+.+)",
            r"(?P<task>copy\s+.+\s+from\s+.+\s+to\s+.+)",
            r"(?P<task>(?:switch|close|open)\s+(?:browser\s+)?tab.*)",
            r"(?P<task>(?:press|hit|tap|send)\s+(?:ctrl|control|alt|shift|win|windows|cmd|command|enter|tab|escape|esc|space|backspace|delete|del|home|end|pageup|pagedown|up|down|left|right|f\d{1,2})(?:\s*\+|\s|$).*)",
        ],
        skill_name="computer_control",
        param_extractor=lambda match: {"task": match.group("task").strip()},
        description="General app/browser/desktop automation",
    ),
    GateRule(
        rule_id="open_app",
        patterns=[
            r"open\s+(?P<app>[a-zA-Z0-9+#._-]+(?:\s+[a-zA-Z0-9+#._-]+)?)\s*$",
            r"launch\s+(?P<app>[a-zA-Z0-9+#._-]+(?:\s+[a-zA-Z0-9+#._-]+)?)\s*$",
            r"start\s+(?P<app>[a-zA-Z0-9+#._-]+(?:\s+[a-zA-Z0-9+#._-]+)?)\s*$",
        ],
        skill_name="open_app",
        param_extractor=lambda match: {"app": match.group("app").strip().lower()},
        description="Open a single application or web service",
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
        rule_id="system_status_full",
        patterns=[
            # "check my system" variants with anything in between
            r".*check\s+(?:how(?:'s|s)?\s+)?(?:my\s+)?(?:the\s+)?(?:system|pc|computer|machine)\s*(?:condition|status|stats|health|performance|info|information|doing|running)?.*",

            # "what's my system" variants
            r".*what(?:'s|s|\s+is)\s+(?:my\s+)?(?:the\s+)?(?:system|pc|computer)\s+(?:condition|status|stats|health|performance|doing|like).*",

            # "how is my system"
            r".*how\s+(?:is|'s)\s+(?:my\s+)?(?:the\s+)?(?:system|pc|computer)\s*(?:doing|running|performing|condition)?.*",

            # "report my system stats/condition"
            r".*report\s+(?:me\s+)?(?:my\s+)?(?:system|pc|computer)\s+(?:stats|status|condition|health|info|performance).*",

            # bare "system condition/status/stats"
            r".*(?:system|pc|computer)\s+(?:condition|status|stats|health|check|info|performance).*",

            # "tell me about my system"
            r".*tell\s+me\s+(?:about\s+)?(?:my\s+)?(?:system|pc|computer)\s*(?:stats|status|condition|info)?.*",

            # "check hows everything" / "how is everything"
            r".*(?:check\s+)?how(?:'s|s|\s+is)\s+everything\s*(?:going|running|looking|doing)?.*",
            r".*(?:everything|all)\s+(?:good|ok|okay|fine|working|running)\s*\?*.*",
        ],
        skill_name="system_monitor",
        param_extractor=lambda m: {"action": "status"},
        description="Show full system status",
    ),
    GateRule(
        rule_id="check_ram_full",
        patterns=[
            r".*check\s+(?:how(?:'s|s)?\s+)?(?:my\s+)?(?:the\s+)?(?:ram|memory|mem)\s*(?:usage|use|level|status|condition|doing)?.*",
            r".*what(?:'s|s|\s+is)\s+(?:my\s+)?(?:the\s+)?(?:ram|memory)\s*(?:usage|use|used|level|like|at)?.*",
            r".*how\s+(?:much\s+)?(?:ram|memory)\s+(?:am\s+i\s+using|is\s+(?:being\s+)?used|do\s+i\s+have|is\s+(?:left|free|available)).*",
            r".*(?:ram|memory|mem)\s+(?:usage|use|check|status|level|info).*",
            r".*show\s+(?:my\s+)?(?:ram|memory)\s*(?:usage|stats|info)?.*",
        ],
        skill_name="system_monitor",
        param_extractor=lambda m: {"action": "status"},
        description="Check RAM usage",
    ),
    GateRule(
        rule_id="check_cpu_full",
        patterns=[
            r".*check\s+(?:how(?:'s|s)?\s+)?(?:my\s+)?(?:the\s+)?(?:cpu|processor|processing)\s*(?:usage|use|level|status|condition|doing|load)?.*",
            r".*what(?:'s|s|\s+is)\s+(?:my\s+)?(?:the\s+)?(?:cpu|processor)\s*(?:usage|use|used|level|load|at)?.*",
            r".*how\s+(?:much\s+)?(?:cpu|processor)\s+(?:am\s+i\s+using|is\s+(?:being\s+)?used|is\s+it\s+at).*",
            r".*(?:cpu|processor)\s+(?:usage|use|check|status|level|load|info).*",
            r".*show\s+(?:my\s+)?(?:cpu|processor)\s*(?:usage|stats|info)?.*",
        ],
        skill_name="system_monitor",
        param_extractor=lambda m: {"action": "status"},
        description="Check CPU usage",
    ),
    GateRule(
        rule_id="check_disk_full",
        patterns=[
            r".*check\s+(?:how(?:'s|s)?\s+)?(?:my\s+)?(?:the\s+)?(?:disk|storage|drive|hard\s*drive|ssd|hdd)\s*(?:usage|use|space|status|condition)?.*",
            r".*what(?:'s|s|\s+is)\s+(?:my\s+)?(?:the\s+)?(?:disk|storage|drive)\s*(?:space|usage|used|free|available|left)?.*",
            r".*how\s+(?:much\s+)?(?:disk\s+space|storage)\s+(?:do\s+i\s+have|is\s+(?:left|free|used|available)).*",
            r".*(?:disk|storage|drive)\s+(?:space|usage|use|check|status|info).*",
        ],
        skill_name="system_monitor",
        param_extractor=lambda m: {"action": "status"},
        description="Check disk space",
    ),
    GateRule(
        rule_id="check_gpu_full",
        patterns=[
            r".*check\s+(?:how(?:'s|s)?\s+)?(?:my\s+)?(?:the\s+)?(?:gpu|graphics\s*card|graphics|vram|video\s*card)\s*(?:condition|status|usage|info|doing)?.*",
            r".*what(?:'s|s|\s+is)\s+(?:my\s+)?(?:gpu|graphics\s*card|graphics)\s*(?:doing|status|condition|usage|temp(?:erature)?)?.*",
            r".*(?:gpu|graphics\s*card|graphics)\s+(?:status|info|check|condition|usage|temp(?:erature)?).*",
        ],
        skill_name="system_monitor",
        param_extractor=lambda m: {"action": "status"},
        description="Check GPU status",
    ),
    GateRule(
        rule_id="monitor_resource",
        patterns=[
            r"(?:monitor|watch|track|keep (?:an\s+)?eye on)\s+(?:my\s+)?(?:ram|cpu|memory|disk|gpu)\s*(?:usage)?(?:\s+(?:above|over|exceeds?)\s+(?P<threshold>\d+)\s*%?)?",
            r"alert\s+(?:me\s+)?(?:if|when)\s+(?:my\s+)?(?:ram|cpu|memory)\s+(?:goes?\s+)?(?:above|over|exceeds?)\s+(?P<threshold>\d+)\s*%?",
            r"notify\s+(?:me\s+)?(?:if|when)\s+(?:my\s+)?(?:ram|cpu|memory)\s+(?:usage\s+)?(?:goes?\s+)?(?:above|over|exceeds?)\s+(?P<threshold>\d+)\s*%?",
        ],
        skill_name="system_monitor",
        param_extractor=lambda m: {
            "action": "monitor",
            "metric": "ram",
            "threshold": float(m.group("threshold")) if "threshold" in m.groupdict() and m.group("threshold") else 80.0,
        },
        description="Monitor resource with threshold",
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
            r"remind me (?:in )?(?P<delay>[\d]+\s*(?:second|minute|min|hour|hr|sec)[s]?)\s+(?:to\s+)?(?P<message>.+)",
            r"remind me (?:at|by|before)\s+(?P<delay>[\d]{1,2}(?::\d{2})?\s*(?:am|pm|o.?clock)?)\s+(?:to\s+)?(?P<message>.+)",
            r"set (?:a\s+)?reminder (?:for|in)\s+(?P<delay>.+?)\s+(?:to\s+)?(?P<message>.+)",
            r"set (?:a\s+)?reminder (?:at|by)\s+(?P<delay>[\d]{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+(?:to\s+)?(?P<message>.+)",
            r"remind me (?:to\s+)?(?P<message>.+?)\s+(?:in|after)\s+(?P<delay>[\d]+\s*(?:second|minute|min|hour|hr)[s]?)",
            r"set (?:a\s+)?reminder (?:to|at|for|by)\s+(?P<delay>[\d]{1,2}(?::\d{2})?\s*(?:am|pm|o.?clock)?)",
        ],
        skill_name="reminder",
        param_extractor=_extract_reminder_params,
        description="Set a timed reminder",
    ),
    GateRule(
        rule_id="set_alarm",
        patterns=[
            r"set (?:an?\s+)?alarm (?:at|for)\s+(?P<time>[\d]{1,2}(?::\d{2})?\s*(?:am|pm|o.?clock)?)\s*(?:(?:for\s+)?(?:today|tomorrow|tonight))?",
            r"wake me (?:up\s+)?at\s+(?P<time>[\d]{1,2}(?::\d{2})?\s*(?:am|pm|o.?clock)?)",
            r"alarm (?:at|for)\s+(?P<time>[\d]{1,2}(?::\d{2})?\s*(?:am|pm|o.?clock)?)",
        ],
        skill_name="reminder",
        param_extractor=lambda match: {
            "message": "Alarm",
            "delay": match.group("time").strip(),
            "is_alarm": True,
        },
        description="Set an alarm at a specific clock time",
    ),
    GateRule(
        rule_id="gui_click",
        patterns=[
            r"click (?:the\s+)?(?:button\s+)?(?:labeled\s+|named\s+|called\s+)?(?:\")?(?P<element>[^\"]+?)(?:\")?\s*(?:button|link|tab|checkbox)?",
            r"press (?:the\s+)?(?P<element>.+?)\s+(?:button|key|tab)",
            r"select (?:the\s+)?(?P<element>.+?)\s+(?:option|item|tab|button)",
        ],
        skill_name="gui_automate",
        param_extractor=lambda m: {
            "action": "click",
            "element": m.group("element").strip()
        },
        description="Click a UI element by name",
    ),
    GateRule(
        rule_id="run_code",
        patterns=[
            r"(?:run|execute|write and run|create and run)\s+(?:a\s+)?(?:python\s+)?(?:script|code|program)\s+(?:to\s+)?(?P<task>.+)",
            r"(?:write|generate)\s+(?:python\s+)?code\s+(?:to\s+|that\s+)?(?P<task>.+)\s+and\s+(?:run|execute)\s+it",
            r"python:\s+(?P<task>.+)",
            r"code:\s+(?P<task>.+)",
        ],
        skill_name="run_code",
        param_extractor=lambda m: {"task": m.group("task").strip()},
        description="Generate and execute Python code for a task",
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
        rule_id="set_env_var",
        patterns=[
            r"set\s+(?P<var>JARVIS_[A-Z_]+)\s*=\s*(?P<val>\S+)",
            r"enable\s+(?P<var>JARVIS_[A-Z_]+)",
            r"disable\s+(?P<var>JARVIS_[A-Z_]+)",
            r"turn\s+(?:on|off)\s+(?P<var>JARVIS_[A-Z_]+)",
        ],
        skill_name="__set_env__",
        param_extractor=_set_env_params,
        description="Set a Jarvis environment variable",
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
        rule_id="recall_preferences",
        patterns=[
            r"(?:what|do you know) (?:do i|have i told you|are my) (?:like|prefer|enjoy|favorite|love)",
            r"(?:what|do you) (?:remember|know|recall) about me",
            r"what do you (?:remember|know|recall) about me",
            r"(?:tell me|what are) my (?:preferences|likes|favorites|interests)",
            r"do you remember (?:what|that) i (?:like|love|prefer|enjoy|told)",
            r"what do i like",
            r"what are my favorites\??",
        ],
        skill_name="__recall_facts__",
        param_extractor=lambda match: {},
        description="Recall stored personal facts about the user",
    ),
    GateRule(
        rule_id="web_summary",
        patterns=[
            r"summari[sz]e (?:everything about|all about|about|info about)?\s*(?P<topic>.+)",
            r"(?:tell me|what do you know) about (?P<topic>.+)",
            r"(?:give me|get me|find) (?:information|info|details|summary) (?:about|on|regarding) (?P<topic>.+)",
            r"research (?P<topic>.+)",
            r"what(?:'s| is) (?:the latest|new) (?:about|on|with|in) (?P<topic>.+)",
            r"who is (?P<topic>.+)",
            r"what happened (?:with|to|in) (?P<topic>.+)",
        ],
        skill_name="web_summary",
        param_extractor=lambda match: {"topic": match.group("topic").strip()},
        description="Search web and summarize information about a topic",
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
