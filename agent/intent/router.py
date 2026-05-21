"""
agent/intent/router.py

Maps Intent to skill params.
Single source of truth for intent-to-skill mapping.
"""

import logging

from agent.intent.schema import Intent, IntentName

logger = logging.getLogger("jarvis.intent.router")

INTENT_TO_SKILL: dict[IntentName, str] = {
    IntentName.SYSTEM_CHECK: "system_monitor",
    IntentName.SYSTEM_MONITOR: "system_monitor",
    IntentName.OPEN_APP: "open_app",
    IntentName.OPEN_AND_SEARCH: "open_and_search",
    IntentName.OPEN_AND_TYPE: "open_and_type",
    IntentName.OPEN_AND_PLAY: "open_search_and_play",
    IntentName.WEB_BROWSE: "browse",
    IntentName.WEB_SEARCH: "web_search",
    IntentName.WEB_SUMMARY: "web_summary",
    IntentName.COMPOSE_EMAIL: "compose_email",
    IntentName.SEND_EMAIL: "send_email",
    IntentName.SET_REMINDER: "reminder",
    IntentName.SET_ALARM: "reminder",
    IntentName.RUN_CODE: "run_code",
    IntentName.FILE_SEARCH: "system_search",
    IntentName.READ_FILE: "read_report",
    IntentName.LEARN_SKILL: "__teach_skill__",
    IntentName.LIST_SKILLS: "list_skills",
    IntentName.SET_CONFIG: "__set_env__",
    IntentName.GUI_CLICK: "gui_automate",
    IntentName.GUI_TYPE: "gui_automate",
    IntentName.COMPUTER_USE: "computer_control",
    IntentName.CHAT: "respond",
    IntentName.GREETING: "__direct_response__",
    IntentName.FAREWELL: "__direct_response__",
    IntentName.ACKNOWLEDGEMENT: "__direct_response__",
    IntentName.WEATHER: "weather",
    IntentName.PNR: "pnr",
    IntentName.TRAIN: "train",
    IntentName.CODABASE_EXPLORE: "codebase_explorer",
    IntentName.DEEP_RESEARCH: "deep_research",
    IntentName.UNKNOWN: "respond",
}


def route(intent: Intent) -> tuple[str, dict]:
    skill_name = INTENT_TO_SKILL.get(intent.name, "respond")
    params = intent.to_skill_params()

    if skill_name == "system_monitor":
        params.setdefault("action", "status")

    if intent.name == IntentName.SET_ALARM:
        params["is_alarm"] = True
        params.setdefault("message", "Alarm")

    if skill_name == "gui_automate":
        if intent.name == IntentName.GUI_CLICK:
            params["action"] = "click"
        elif intent.name == IntentName.GUI_TYPE:
            params["action"] = "type" if params.get("app") else "type_active"

    if intent.name == IntentName.COMPUTER_USE:
        params["task"] = params.get("goal") or params.get("task") or intent.raw_input

    if intent.name == IntentName.DEEP_RESEARCH:
        params["topic"] = params.get("topic") or params.get("query") or intent.raw_input

    if intent.name == IntentName.CODABASE_EXPLORE:
        params["query"] = params.get("query") or params.get("task") or intent.raw_input

    logger.debug("Routed %s to %s with params %s", intent.name.value, skill_name, list(params.keys()))
    return skill_name, params
