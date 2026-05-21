"""
agent/intent/llm_classifier.py

LLM-based intent classifier fallback when rules do not match.
"""

import json
import logging

from agent.intent.schema import Entity, INTENT_CATALOG, Intent, IntentName
from models.llm import call_llm_cached

logger = logging.getLogger("jarvis.intent.llm")

_SYSTEM_PROMPT = """You are an intent classifier for an AI assistant.
Classify the user input into exactly one intent from this list:

""" + "\n".join(
    f'- {name.value}: {data["description"]}'
    for name, data in INTENT_CATALOG.items()
) + """

Also extract relevant entities mentioned in the input.

Return ONLY valid JSON:
{
  "intent": "intent_name_here",
  "confidence": 0.0,
  "entities": {
    "entity_name": "entity_value"
  }
}

Rules:
- "ntg", "ok", "cool", "thanks" and similar short acknowledgements = acknowledgement
- Single words that are not commands = acknowledgement
- Always extract email addresses as entity "to" for email intents
- Extract app names, queries, topics as appropriate entities
- If truly unsure use intent "chat"
"""


def classify_with_llm(raw_input: str) -> Intent:
    try:
        # Intent classification uses main LLM (qwen3:8b).
        # This is the fallback when rules do not match.
        response = call_llm_cached(
            system_key="intent_classifier",
            system=_SYSTEM_PROMPT,
            user=raw_input,
            temperature=0.0,
            max_tokens=150,
        )

        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip().rstrip("```").strip()

        data = json.loads(cleaned)
        intent_name_str = data.get("intent", "chat")
        confidence = float(data.get("confidence", 0.8))
        raw_entities = data.get("entities", {})

        try:
            intent_name = IntentName(intent_name_str)
        except ValueError:
            logger.warning("Unknown intent name from LLM: %s", intent_name_str)
            intent_name = IntentName.CHAT

        entities = {
            key: Entity(name=key, value=str(value))
            for key, value in raw_entities.items()
            if value
        }

        return Intent(
            name=intent_name,
            entities=entities,
            confidence=confidence,
            raw_input=raw_input,
            classification_source="llm",
        )

    except json.JSONDecodeError as exc:
        logger.warning("LLM classifier returned invalid JSON: %s", exc)
    except Exception as exc:
        logger.error("LLM classification failed: %s", exc)

    return Intent(
        name=IntentName.CHAT,
        entities={"message": Entity(name="message", value=raw_input)},
        confidence=0.5,
        raw_input=raw_input,
        classification_source="fallback",
    )
