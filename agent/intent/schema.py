"""
agent/intent/schema.py

Defines every intent Jarvis can understand.
This is the single source of truth for what Jarvis can do.
Adding a new capability starts by adding an Intent here first.
"""

from dataclasses import dataclass, field
from enum import Enum


class IntentName(str, Enum):
    SYSTEM_CHECK = "system_check"
    SYSTEM_MONITOR = "system_monitor"

    OPEN_APP = "open_app"
    OPEN_AND_SEARCH = "open_and_search"
    OPEN_AND_TYPE = "open_and_type"
    OPEN_AND_PLAY = "open_and_play"

    WEB_BROWSE = "web_browse"
    WEB_SEARCH = "web_search"
    WEB_SUMMARY = "web_summary"

    COMPOSE_EMAIL = "compose_email"
    SEND_EMAIL = "send_email"

    SET_REMINDER = "set_reminder"
    SET_ALARM = "set_alarm"
    RUN_CODE = "run_code"
    FILE_SEARCH = "file_search"
    READ_FILE = "read_file"

    WEATHER = "weather"
    PNR = "pnr"
    TRAIN = "train"
    CHAT = "chat"
    GREETING = "greeting"
    FAREWELL = "farewell"
    ACKNOWLEDGEMENT = "acknowledgement"

    LEARN_SKILL = "learn_skill"
    LIST_SKILLS = "list_skills"
    SET_CONFIG = "set_config"

    GUI_CLICK = "gui_click"
    GUI_TYPE = "gui_type"
    COMPUTER_USE = "computer_use"
    CODABASE_EXPLORE = "codebase_explore"
    DEEP_RESEARCH = "deep_research"

    UNKNOWN = "unknown"


@dataclass
class Entity:
    """A named piece of information extracted from user input."""

    name: str
    value: str
    confidence: float = 1.0
    raw_span: str = ""


@dataclass
class Intent:
    """A classified user intent with extracted entities."""

    name: IntentName
    entities: dict[str, Entity] = field(default_factory=dict)
    confidence: float = 1.0
    raw_input: str = ""
    classification_source: str = ""
    requires_clarification: bool = False
    clarification_question: str = ""

    def get(self, entity_name: str, default: str = "") -> str:
        entity = self.entities.get(entity_name)
        return entity.value if entity else default

    def has(self, entity_name: str) -> bool:
        return entity_name in self.entities

    def to_skill_params(self) -> dict:
        return {name: entity.value for name, entity in self.entities.items()}


INTENT_CATALOG: dict[IntentName, dict] = {
    IntentName.SYSTEM_CHECK: {
        "description": "User wants to see system resource stats (CPU, RAM, disk, GPU)",
        "examples": [
            "check my system",
            "check hows my system",
            "whats my cpu usage",
            "how is my ram",
            "system stats",
            "check hows my system and report me its stats",
            "what is my disk space",
            "show me my gpu condition",
            "how much memory am i using",
            "report system health",
        ],
        "entities": {"metric": "optional: cpu|ram|disk|gpu|all"},
        "skill": "system_monitor",
    },
    IntentName.OPEN_APP: {
        "description": "User wants to open a single application or website",
        "examples": ["open chrome", "launch notepad", "start vscode", "open gmail", "open youtube"],
        "entities": {"app": "required: the app or service name"},
        "skill": "open_app",
    },
    IntentName.OPEN_AND_SEARCH: {
        "description": "User wants to open an app and search for something in it",
        "examples": [
            "open youtube and search for telugu songs",
            "open google and search for python tutorials",
            "open firefox and find tamilnadu cm",
            "search youtube for lofi music",
        ],
        "entities": {"app": "required: which app to open", "query": "required: what to search for"},
        "skill": "open_and_search",
    },
    IntentName.OPEN_AND_PLAY: {
        "description": "User wants to open an app, search, and play/interact with first result",
        "examples": [
            "open youtube search telugu songs and play the first one",
            "open spotify search lofi and play first song",
            "open youtube, search raid 2 trailer and watch it",
        ],
        "entities": {"app": "required: which app", "query": "required: what to search", "action": "optional"},
        "skill": "open_search_and_play",
    },
    IntentName.OPEN_AND_TYPE: {
        "description": "User wants to open an app and type text into it",
        "examples": ["open notepad and type hello", "open word and write my essay"],
        "entities": {"app": "required: which app to open", "text": "required: what to type"},
        "skill": "open_and_type",
    },
    IntentName.WEB_BROWSE: {
        "description": "User wants to navigate to a specific URL",
        "examples": ["go to github.com", "open https://example.com", "browse to google.com"],
        "entities": {"url": "required: the URL to open"},
        "skill": "browse",
    },
    IntentName.WEB_SEARCH: {
        "description": "User wants to search the web for something",
        "examples": ["search for python tutorials", "google machine learning", "look up telugu movies"],
        "entities": {"query": "required: search query"},
        "skill": "browse",
    },
    IntentName.WEB_SUMMARY: {
        "description": "User wants a summary or information about a topic",
        "examples": [
            "summarise everything about tamilnadu cm",
            "tell me about elon musk",
            "who is the current prime minister of india",
        ],
        "entities": {"topic": "required: the topic to research"},
        "skill": "web_summary",
    },
    IntentName.COMPOSE_EMAIL: {
        "description": "User wants to compose or send an email",
        "examples": ["send email to john@example.com about the meeting"],
        "entities": {"to": "required: recipient", "body": "optional", "subject": "optional"},
        "skill": "compose_email",
    },
    IntentName.SET_REMINDER: {
        "description": "User wants to set a reminder at a specific time or after a delay",
        "examples": ["remind me in 5 minutes to check my code", "set a reminder at 10 o clock"],
        "entities": {"message": "required", "delay": "required"},
        "skill": "reminder",
    },
    IntentName.FILE_SEARCH: {
        "description": "User wants to find a file or folder on their computer",
        "examples": ["find folder spider man on my pc", "search for notes.txt on my computer"],
        "entities": {"query": "required", "type": "optional: file|folder|any"},
        "skill": "system_search",
    },
    IntentName.RUN_CODE: {
        "description": "User wants to run or execute code",
        "examples": ["run a python script to rename files", "python: print hello world"],
        "entities": {"task": "required: what the code should do"},
        "skill": "run_code",
    },
    IntentName.LEARN_SKILL: {
        "description": "User wants to teach Jarvis a new skill",
        "examples": ["teach you how to open my email", "learn this workflow"],
        "entities": {"raw_input": "required: full instruction"},
        "skill": "teach_skill",
    },
    IntentName.WEATHER: {
        "description": "User wants to check weather for a city",
        "examples": [
            "what is the weather in Hyderabad",
            "check temperature in London",
            "weather report for Delhi",
        ],
        "entities": {"city": "optional: city name"},
        "skill": "weather",
    },
    IntentName.PNR: {
        "description": "User wants to check Indian Railway PNR status",
        "examples": ["check PNR 1234567890", "PNR status", "what is my PNR status"],
        "entities": {"pnr": "required: 10-digit PNR number"},
        "skill": "pnr",
    },
    IntentName.TRAIN: {
        "description": "User wants to check live train status",
        "examples": ["where is train 12345", "live status of train 12701", "train running status"],
        "entities": {"train_number": "required: train number"},
        "skill": "train",
    },
    IntentName.SET_CONFIG: {
        "description": "User wants to configure a Jarvis setting",
        "examples": ["set JARVIS_VISION_VERIFY=true", "enable screenshot verification"],
        "entities": {"var": "required: setting name", "val": "required: setting value"},
        "skill": "__set_env__",
    },
    IntentName.COMPUTER_USE: {
        "description": "General computer automation task requiring screen reading",
        "examples": [
            "go to spotify and create a party playlist",
            "fill out this form",
            "find and click the settings button",
            "open vscode and create a new file",
        ],
        "entities": {"goal": "required: what to accomplish"},
        "skill": "computer_control",
    },
    IntentName.CHAT: {
        "description": "User wants to have a conversation or ask a question",
        "examples": ["what is machine learning", "explain quantum computing"],
        "entities": {"message": "required: the question or message"},
        "skill": "respond",
    },
    IntentName.GREETING: {
        "description": "User is greeting Jarvis",
        "examples": ["hi", "hello", "hey jarvis", "good morning"],
        "entities": {},
        "skill": "__direct_response__",
    },
    IntentName.CODABASE_EXPLORE: {
        "description": "User wants to explore or understand how Jarvis code works",
        "examples": [
            "how does the screenshot agent work",
            "explain the executor architecture",
            "how does jarvis route intents to skills",
            "show me the computer use agent code",
        ],
        "entities": {"query": "required: what to explore", "mode": "optional: read|runtime"},
        "skill": "codebase_explorer",
    },
    IntentName.DEEP_RESEARCH: {
        "description": "User wants deep multi-query research comparing topics or covering multiple angles",
        "examples": [
            "compare jarvis screenshot mode to claude computer use",
            "deep research on local LLM agents",
            "research open source computer use agents and compare features",
        ],
        "entities": {"topic": "required: research topic", "depth": "optional: number of sub-queries"},
        "skill": "deep_research",
    },
    IntentName.ACKNOWLEDGEMENT: {
        "description": "User acknowledging or saying nothing significant",
        "examples": ["ok", "thanks", "cool", "ntg", "nothing", "nm", "nah", "got it"],
        "entities": {},
        "skill": "__direct_response__",
    },
}
