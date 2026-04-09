import json

import ollama


CLASSIFIER_MODEL = "gemma:1b"
FALLBACK_RESULT = {"type": "fast", "confidence": 0.0}
ALLOWED_TYPES = {"skill", "fast", "smart"}


def _extract_json_object(text: str) -> dict | None:
    content = str(text or "").strip()
    if not content:
        return None

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        data = json.loads(content[start:end + 1])
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def classify_query(query: str) -> dict:
    cleaned_query = str(query).strip()
    if not cleaned_query:
        return dict(FALLBACK_RESULT)

    system_prompt = (
        "Classify the user query into:\n"
        "- skill -> direct action (open, search, play)\n"
        "- fast -> simple conversation\n"
        "- smart -> complex reasoning\n\n"
        "Respond ONLY in JSON:\n"
        '{"type":"...", "confidence":0.00}'
    )

    try:
        response = ollama.chat(
            model=CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": cleaned_query},
            ],
            options={
                "temperature": 0.1,
                "num_predict": 60,
            },
            keep_alive=300,
        )
        data = _extract_json_object(response.get("message", {}).get("content", ""))
        if not data:
            return dict(FALLBACK_RESULT)

        route_type = str(data.get("type", "")).strip().lower()
        if route_type not in ALLOWED_TYPES:
            return dict(FALLBACK_RESULT)

        try:
            confidence = float(data.get("confidence", 0.0))
        except Exception:
            confidence = 0.0

        confidence = max(0.0, min(1.0, confidence))
        return {"type": route_type, "confidence": confidence}
    except Exception:
        return dict(FALLBACK_RESULT)
