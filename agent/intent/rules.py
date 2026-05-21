"""
agent/intent/rules.py

Rule-based intent classifier.
Uses pure-Python linguistic patterns for common deterministic intents.
Falls back to the LLM classifier for ambiguous inputs.
"""

import re
from typing import Optional

from agent.intent.schema import Entity, Intent, IntentName

try:
    from skills.app_registry import get_app_registry
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip().rstrip(".,!?"))


def _make_intent(
    name: IntentName,
    raw: str,
    entities: dict | None = None,
    confidence: float = 1.0,
) -> Intent:
    entity_objs = {}
    if entities:
        for key, value in entities.items():
            if value is not None and str(value).strip():
                entity_objs[key] = Entity(name=key, value=str(value).strip())
    return Intent(
        name=name,
        entities=entity_objs,
        confidence=confidence,
        raw_input=raw,
        classification_source="rule",
    )


_GREETINGS = {
    "hi", "hello", "hey", "howdy", "sup", "yo", "hi there",
    "hey there", "hello there", "good morning", "good afternoon",
    "good evening", "morning", "evening",
    "how are you", "how's it going", "what's up", "wassup",
    "whats up", "how are ya", "howdy there", "greetings",
    "what's good", "how do you do", "nice to meet you",
}

_GREETING_STEMS = {"hi", "hello", "hey", "howdy", "sup", "yo", "how are", "whats", "what's"}

_GREETING_PATTERNS = [
    re.compile(r"^(hi|hello|hey|howdy|sup|yo)(\s+(there|ya|jarvis|everyone))?$", re.I),
    re.compile(r"^(what'?s up|how'?s it going|how are you|how are ya|howdy there|"
               r"how do you do|whats good|nice to meet you)", re.I),
]

_ACKNOWLEDGEMENTS = {
    "ok", "okay", "k", "kk", "sure", "yep", "yup", "yeah", "yes",
    "no", "nope", "nah", "got it", "understood", "alright", "fine",
    "thanks", "thank you", "thx", "ty", "cheers", "np",
    "cool", "great", "nice", "awesome", "perfect", "good", "bad",
    "lol", "haha", "hehe", "wow", "ntg", "ntn", "nothing", "nothin",
    "nada", "nm", "not much", "nmh", "nothing much", "nthing",
    "bye", "goodbye", "later", "cya", "see ya", "gn", "ttyl", "brb",
    "ah", "oh", "hmm", "ugh", "faaaah",
}

_FAREWELL_TRIGGERS = {"quit", "exit", "bye", "goodbye", "later", "stop jarvis", "shut down"}


def _classify_trivial(text: str, raw: str) -> Optional[Intent]:
    if text in _GREETINGS:
        return _make_intent(IntentName.GREETING, raw, {"response": "Hello! How can I help you today?"})
    for pat in _GREETING_PATTERNS:
        if pat.match(text):
            return _make_intent(IntentName.GREETING, raw, {"response": "Hello! How can I help you today?"})
    if text in _FAREWELL_TRIGGERS:
        return _make_intent(IntentName.FAREWELL, raw, {"response": "Later."})
    if text in _ACKNOWLEDGEMENTS:
        return _make_intent(IntentName.ACKNOWLEDGEMENT, raw, {"response": "Got it. Let me know if you need anything."})
    if len(text.split()) == 1 and len(text) <= 4:
        return _make_intent(IntentName.ACKNOWLEDGEMENT, raw, {"response": "Got it."})
    return None


_SYSTEM_METRICS = {"cpu", "ram", "memory", "disk", "storage", "gpu", "graphics", "battery"}
_SYSTEM_WORDS = {"system", "pc", "computer", "device"}
_SYSTEM_VERBS = {"check", "show", "report", "display", "tell", "what", "how", "whats", "hows"}


def _classify_system_check(text: str, raw: str) -> Optional[Intent]:
    words = set(text.split())
    has_system_word = bool(words & _SYSTEM_WORDS)
    metrics = words & _SYSTEM_METRICS
    has_verb = bool(words & _SYSTEM_VERBS)

    if has_verb and (metrics or has_system_word):
        metric_val = next(iter(metrics)) if metrics else "all"
        if metric_val == "memory":
            metric_val = "ram"
        if metric_val == "graphics":
            metric_val = "gpu"
        return _make_intent(IntentName.SYSTEM_CHECK, raw, {"metric": metric_val})

    indicator_words = {"usage", "status", "stats", "info", "condition", "health", "level", "temperature"}
    if metrics and (words & indicator_words):
        metric_val = next(iter(metrics))
        if metric_val == "memory":
            metric_val = "ram"
        if metric_val == "graphics":
            metric_val = "gpu"
        return _make_intent(IntentName.SYSTEM_CHECK, raw, {"metric": metric_val})

    return None


_SEPARATORS = r"(?:[,\s]+(?:and|then|also|after|next)?\s*)"


def _match_playable(app_name: str) -> bool:
    """Check if the app supports play (search + click first result)."""
    if not _REGISTRY_AVAILABLE:
        return "youtube" in app_name
    try:
        cap = get_app_registry().get(app_name)
        return cap is not None and cap.supports_play
    except Exception:
        return "youtube" in app_name


def _classify_open_pattern(text: str, raw: str) -> Optional[Intent]:
    m = re.match(
        r"(?:open|launch|start)\s+(\w+)" + _SEPARATORS
        + r"(?:search|find|look\s*up)\s+(?:for\s+)?(.+?)\s+and\s+"
        + r"(?:play|watch|listen|stream)\s+(?:the\s+)?(?:first|top)?\s*(?:one|result|video|song)?",
        text,
    )
    if m:
        app = m.group(1)
        if _match_playable(app):
            return _make_intent(IntentName.OPEN_AND_PLAY, raw, {"app": app, "query": m.group(2)})
        return _make_intent(IntentName.OPEN_AND_SEARCH, raw, {"app": app, "query": m.group(2)})

    m = re.match(
        r"(?:open|launch|start)\s+(\w+)" + _SEPARATORS
        + r"(?:search|find)\s+(?:for\s+)?(.+?)" + _SEPARATORS
        + r"(?:play|watch|stream|listen|select|click)\s+(?:the\s+)?(?:first|top)?",
        text,
    )
    if m:
        app = m.group(1)
        if _match_playable(app):
            return _make_intent(IntentName.OPEN_AND_PLAY, raw, {"app": app, "query": m.group(2)})
        return _make_intent(IntentName.OPEN_AND_SEARCH, raw, {"app": app, "query": m.group(2)})

    m = re.match(
        r"(?:open|launch|start)\s+(\w+)" + _SEPARATORS
        + r"(?:search|find|look\s*up)\s+(?:for\s+)?(.+)$",
        text,
    )
    if m:
        return _make_intent(IntentName.OPEN_AND_SEARCH, raw, {"app": m.group(1), "query": m.group(2)})

    m = re.match(
        r"(?:open|launch|start)\s+(\w+)" + _SEPARATORS
        + r"(?:type|write|input|enter)\s+(.+)$",
        text,
    )
    if m:
        return _make_intent(IntentName.OPEN_AND_TYPE, raw, {"app": m.group(1), "text": m.group(2)})

    m = re.match(r"(?:open|launch|start)\s+([a-zA-Z0-9][\w\s]{0,25}?)\s*$", text)
    if m:
        app = m.group(1).strip()
        if len(app.split()) <= 3 and not any(word in app for word in ["and", "then", "for", "with", "to"]):
            return _make_intent(IntentName.OPEN_APP, raw, {"app": app})
    return None


def _classify_deep_research(text: str, raw: str) -> Optional[Intent]:
    if re.match(r"(?:compare|comparison|vs|versus)\s+.+\s+(?:and|to|vs)\s+", text):
        return _make_intent(IntentName.DEEP_RESEARCH, raw, {"topic": raw, "depth": "4", "format": "auto"})
    if re.match(r"(?:deep\s+research|deep.dive|comprehensive\s+research|multi.query)\s+(?:on|about|into)?\s*(.+)", text):
        topic = re.match(r"(?:deep\s+research|deep.dive|comprehensive\s+research|multi.query)\s+(?:on|about|into)?\s*(.+)", text).group(1).strip()
        return _make_intent(IntentName.DEEP_RESEARCH, raw, {"topic": topic, "depth": "4"})
    return None


def _classify_codebase_explore(text: str, raw: str) -> Optional[Intent]:
    patterns = [
        r"(?:how|what|where|why|does)\s+(?:does\s+)?(?:the\s+)?(?:jarvis\s+)?(.+?)\s+(?:work|do|look.like|structured|organized)",
        r"(?:explain|describe)\s+(?:the\s+)?(?:jarvis\s+)?(?:code|architecture|design|structure|system)\s+(?:of|for)?\s*(.+)",
        r"(?:show|find|read|open)(?:\s+\w+)?\s+(?:the\s+)?(.+?)\s+(?:code|file|module)\s*$",
        r"(?:how\s+is)\s+(.+)",
    ]
    for pat in patterns:
        m = re.match(pat, text)
        if m:
            return _make_intent(IntentName.CODABASE_EXPLORE, raw, {"query": raw})
    if "codebase" in text and any(w in text for w in ("explore", "explain", "show", "find", "how")):
        return _make_intent(IntentName.CODABASE_EXPLORE, raw, {"query": raw})
    return None


def _classify_computer_use(text: str, raw: str) -> Optional[Intent]:
    """Route broad GUI workflows to the RawVision/Hands computer-control loop."""
    if re.search(r"\b(?:play|watch|listen|stream)\b", text):
        return None

    app_workflow = re.match(
        r"(?:open|launch|start|go\s+to)\s+\w+.*\b"
        r"(?:search|find|look\s*up|create|make|fill|submit|click|select|playlist|new\s+file|settings)\b",
        text,
    )
    if app_workflow:
        return _make_intent(IntentName.COMPUTER_USE, raw, {"goal": raw})

    direct_workflow = re.match(
        r"(?:fill\s+(?:out\s+)?(?:this\s+)?form|find\s+and\s+click\s+.+|"
        r"create\s+.+\s+(?:playlist|file|document))",
        text,
    )
    if direct_workflow:
        return _make_intent(IntentName.COMPUTER_USE, raw, {"goal": raw})

    return None


def _classify_reminder(text: str, raw: str) -> Optional[Intent]:
    m = re.match(r"remind\s+me\s+in\s+(.+?)\s+to\s+(.+)$", text)
    if m:
        return _make_intent(IntentName.SET_REMINDER, raw, {"delay": m.group(1), "message": m.group(2)})

    m = re.match(r"remind\s+me\s+to\s+(.+?)\s+(?:in|at|by)\s+(.+)$", text)
    if m:
        return _make_intent(IntentName.SET_REMINDER, raw, {"message": m.group(1), "delay": m.group(2)})

    m = re.match(r"set\s+(?:a\s+)?(?P<kind>reminder|alarm)\s+(?:at|for|to)\s+(?P<delay>[\d:apm\s]+?)(?:\s+(?:to\s+)?(?P<message>.+))?$", text)
    if m:
        name = IntentName.SET_ALARM if m.group("kind") == "alarm" else IntentName.SET_REMINDER
        return _make_intent(name, raw, {"message": (m.group("message") or "reminder"), "delay": m.group("delay")})
    return None


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _classify_email(text: str, raw: str) -> Optional[Intent]:
    email_match = _EMAIL_RE.search(text)
    if not email_match:
        return None
    if not any(trigger in text for trigger in {"send", "email", "mail", "compose", "write", "gmail"}):
        return None
    to = email_match.group(0)
    body_match = re.search(r"(?:about|asking|saying|regarding|sending|with message|inviting|that)\s+(.+)$", text)
    body = body_match.group(1).strip() if body_match else ""
    return _make_intent(IntentName.COMPOSE_EMAIL, raw, {"to": to, "body": body})


_SUMMARY_TRIGGERS = [
    r"(?:summari[sz]e|summarize)\s+(?:everything\s+)?(?:about|on|regarding)?\s*(.+)",
    r"(?:tell\s+me|what\s+do\s+you\s+know)\s+(?:everything\s+)?about\s+(.+)",
    r"(?:who|what|where|when|why|how)\s+is\s+(?:the\s+)?(.+)",
    r"(?:find\s+info|get\s+info|research)\s+(?:about|on)?\s*(.+)",
    r"(?:what\s+is|whats)\s+(.+)",
    r"(?:explain|describe)\s+(.+)",
]


def _classify_web_summary(text: str, raw: str) -> Optional[Intent]:
    for pattern in _SUMMARY_TRIGGERS:
        match = re.match(pattern, text)
        if match:
            topic = match.group(1).strip()
            if len(topic) > 3:
                return _make_intent(IntentName.WEB_SUMMARY, raw, {"topic": topic})
    return None


def _classify_config(text: str, raw: str) -> Optional[Intent]:
    match = re.match(r"set\s+(JARVIS_\w+)\s*=\s*(\S+)", raw.strip(), re.IGNORECASE)
    if match:
        return _make_intent(IntentName.SET_CONFIG, raw, {"var": match.group(1).upper(), "val": match.group(2)})

    match = re.match(r"(enable|disable|turn\s+on|turn\s+off)\s+(JARVIS_\w+)", raw.strip(), re.IGNORECASE)
    if match:
        command = match.group(1).lower()
        val = "true" if command in ("enable", "turn on") else "false"
        return _make_intent(IntentName.SET_CONFIG, raw, {"var": match.group(2).upper(), "val": val})
    return None


_TEACH_TRIGGERS = ["teach you", "learn how to", "remember how to", "train you", "new skill", "teach jarvis"]


def _classify_learn_skill(text: str, raw: str) -> Optional[Intent]:
    if any(trigger in text for trigger in _TEACH_TRIGGERS):
        return _make_intent(IntentName.LEARN_SKILL, raw, {"raw_input": raw})
    return None


def _classify_file_search(text: str, raw: str) -> Optional[Intent]:
    match = re.search(
        r"(?:find|search\s+for|look\s+for|is\s+there)\s+(?:a\s+)?(?:(?P<type>file|folder)\s+)?"
        r"(?:named|called)?\s*(?P<query>\w[\w\s-]{0,40}?)\s*"
        r"(?:on\s+my\s+(?:pc|computer|device|system|desktop))?$",
        text,
    )
    if match and match.group("query"):
        return _make_intent(IntentName.FILE_SEARCH, raw, {"query": match.group("query"), "type": match.group("type") or "any"})
    return None


def _classify_browse(text: str, raw: str) -> Optional[Intent]:
    url_match = re.search(r"https?://\S+", text)
    if url_match:
        return _make_intent(IntentName.WEB_BROWSE, raw, {"url": url_match.group(0)})

    match = re.match(r"(?:go\s+to|browse\s+to?|navigate\s+to|visit)\s+(\S+)", text)
    if match:
        url = match.group(1)
        if not url.startswith("http"):
            url = "https://" + url
        return _make_intent(IntentName.WEB_BROWSE, raw, {"url": url})
    return None


def _classify_gui_action(text: str, raw: str) -> Optional[Intent]:
    click_match = re.match(
        r"(?:click|select|choose|tap)\s+(?:the\s+)?(?P<element>.+?)"
        r"(?:\s+(?:button|link|tab|field|option|menu|icon))?$",
        text,
    )
    if click_match:
        element = click_match.group("element").strip()
        if element:
            return _make_intent(IntentName.GUI_CLICK, raw, {"element": element})

    type_match = re.match(
        r"(?:type|enter|input)\s+(?P<typed_text>.+?)"
        r"(?:\s+(?:in|into|on)\s+(?:the\s+)?(?P<app>[\w\s.-]{1,40}))?$",
        text,
    )
    if type_match:
        typed_text = type_match.group("typed_text").strip()
        app = (type_match.group("app") or "").strip()
        entities = {"text": typed_text}
        if app:
            entities["app"] = app
        if typed_text:
            return _make_intent(IntentName.GUI_TYPE, raw, entities)

    return None


def _classify_web_search(text: str, raw: str) -> Optional[Intent]:
    match = re.match(r"(?:search|google|bing|look\s+up|search\s+for)\s+(?:for\s+)?(.+)", text)
    if match:
        return _make_intent(IntentName.WEB_SEARCH, raw, {"query": match.group(1)})
    return None


_LIST_SKILLS_PHRASES = {
    "list skills", "show skills", "what can you do",
    "what are your skills", "show me your skills", "available skills", "help",
}


def _classify_list_skills(text: str, raw: str) -> Optional[Intent]:
    if text in _LIST_SKILLS_PHRASES:
        return _make_intent(IntentName.LIST_SKILLS, raw)
    return None


def _classify_run_code(text: str, raw: str) -> Optional[Intent]:
    match = re.match(r"(?:run|execute|write\s+and\s+run|create\s+and\s+run)\s+(?:a\s+)?(?:python\s+)?(?:script|code|program)\s+(?:to\s+)?(.+)", text)
    if match:
        return _make_intent(IntentName.RUN_CODE, raw, {"task": match.group(1)})
    if text.startswith("python:") or text.startswith("code:"):
        return _make_intent(IntentName.RUN_CODE, raw, {"task": text.split(":", 1)[1].strip()})
    return None


def _classify_learned(text: str, raw: str) -> Optional[Intent]:
    """Delegate to learned rules registry."""
    _ = text
    try:
        from agent.intent.learned_rules import classify_with_learned_rules

        return classify_with_learned_rules(raw)
    except ImportError:
        return None


_RULE_PIPELINE = [
    _classify_learned,
    _classify_trivial,
    _classify_config,
    _classify_learn_skill,
    _classify_email,
    _classify_reminder,
    _classify_system_check,
    _classify_computer_use,
    _classify_open_pattern,
    _classify_browse,
    _classify_gui_action,
    _classify_web_search,
    _classify_file_search,
    _classify_run_code,
    _classify_list_skills,
    _classify_web_summary,
    _classify_deep_research,
    _classify_codebase_explore,
]


def classify_with_rules(raw_input: str) -> Optional[Intent]:
    text = _normalize(raw_input)
    if not text:
        return None
    for classifier in _RULE_PIPELINE:
        result = classifier(text, raw_input)
        if result is not None:
            return result
    return None
