from typing import Dict, List


INTENT_REGISTRY = {
    "open": ["open", "launch", "start"],
    "search": ["search", "browse"],
    "play": ["play"],
    "find": ["find", "locate"],
    "watch": ["watch"],
}

INTENT_LOOKUP = {
    alias: intent
    for intent, aliases in INTENT_REGISTRY.items()
    for alias in aliases
}

FILLER_WORDS = {
    "for", "the", "a", "an", "to", "on", "in",
    "and", "then", "please", "me",
}

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


def parse_commands(query: str) -> List[Dict]:
    commands: List[Dict] = []
    current_intent = ""
    current_target_tokens: List[str] = []

    for token in tokenize(query):
        intent = INTENT_LOOKUP.get(token)
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
        token for token in tokenize(text)
        if token not in FILLER_WORDS
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
