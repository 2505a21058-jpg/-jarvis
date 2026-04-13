from typing import Dict, List


INTENT_REGISTRY = {
    "open": ["open", "launch", "start"],
    "search": ["search", "browse"],
    "play": ["play"],
    "find": ["find", "locate"],
    "watch": ["watch"],
    "type": ["type", "write", "enter"],
}

INTENT_LOOKUP = {
    alias: intent
    for intent, aliases in INTENT_REGISTRY.items()
    for alias in aliases
}

FILLER_WORDS = {
    "for", "the", "a", "an", "to", "on", "in",
}
CONNECTOR_WORDS = {"and", "then"}

STRIP_CHARS = " \t\r\n,.;:!?()[]{}\"'"


def tokenize(query: str) -> List[str]:
    lowered = str(query).lower().strip()
    if not lowered:
        return []

    tokens: List[str] = []
    for chunk in lowered.split():
        token = chunk.strip(STRIP_CHARS)
        if token:
            tokens.append(token)
    return tokens


def _iter_original_tokens(query: str) -> List[str]:
    text = str(query).strip()
    if not text:
        return []
    return [chunk.strip() for chunk in text.split() if chunk.strip()]


def _intent_key(token: str) -> str:
    return token.strip(STRIP_CHARS).lower()


def parse_commands(query: str) -> List[Dict]:
    commands: List[Dict] = []
    current_intent = ""
    current_target_tokens: List[str] = []
    tokens = _iter_original_tokens(query)

    for index, token in enumerate(tokens):
        token_key = _intent_key(token)
        next_key = _intent_key(tokens[index + 1]) if index + 1 < len(tokens) else ""
        if current_intent and token_key in CONNECTOR_WORDS and next_key in INTENT_LOOKUP:
            continue

        intent = INTENT_LOOKUP.get(token_key)
        if intent:
            if current_intent:
                commands.append({
                    "intent": current_intent,
                    "target": " ".join(current_target_tokens).strip(),
                })
            current_intent = intent
            current_target_tokens = []
            continue

        if current_intent:
            current_target_tokens.append(token)

    if current_intent:
        commands.append({
            "intent": current_intent,
            "target": " ".join(current_target_tokens).strip(),
        })

    return commands


def clean_target(text: str) -> str:
    cleaned_tokens = [
        token for token in _iter_original_tokens(text)
        if _intent_key(token) not in FILLER_WORDS
    ]
    return " ".join(cleaned_tokens).strip()


def normalize_commands(commands: List[Dict]) -> List[Dict]:
    normalized: List[Dict] = []

    for command in commands:
        intent = str(command.get("intent", "")).strip().lower()
        if intent not in INTENT_REGISTRY:
            continue

        target = clean_target(command.get("target", ""))
        if not target and intent == "play":
            target = "music"
        if not target:
            continue

        normalized.append({"intent": intent, "target": target})

    return normalized


def extract_commands(query: str) -> List[Dict]:
    return normalize_commands(parse_commands(query))
