from __future__ import annotations

import json

import pytest

from models import gemma


def test_gemma_default_model_tracks_action_model_default():
    assert gemma._GEMMA_MODEL == "gemma3:4b"
    assert gemma._GEMMA_TIMEOUT == 20


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_is_available_detects_pulled_gemma_model(monkeypatch):
    monkeypatch.setattr(gemma, "_GEMMA_MODEL", "gemma3")
    monkeypatch.setattr(
        gemma.urllib.request,
        "urlopen",
        lambda req, timeout: FakeResponse({"models": [{"name": "gemma3:latest"}]}),
    )

    assert gemma.is_available() is True


def test_call_gemma_json_parses_fenced_json(monkeypatch):
    monkeypatch.setattr(
        gemma,
        "call_gemma",
        lambda prompt, system="", **kwargs: '```json\n{"steps": [{"skill": "open_app", "params": {"app": "chrome"}}]}\n```',
    )

    assert gemma.call_gemma_json("open chrome") == {
        "steps": [{"skill": "open_app", "params": {"app": "chrome"}}]
    }


def test_call_gemma_json_uses_short_token_budget(monkeypatch):
    calls = []

    def fake_call_gemma(prompt, system="", max_tokens=256):
        calls.append(max_tokens)
        return '{"answer": 4}'

    monkeypatch.setattr(gemma, "call_gemma", fake_call_gemma)

    assert gemma.call_gemma_json("2+2") == {"answer": 4}
    assert calls == [512]


def test_call_gemma_vision_sends_screenshot_image(monkeypatch):
    requests = []

    def fake_urlopen(req, timeout):
        requests.append((req, timeout))
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["model"] == "gemma3:4b"
        assert payload["images"] == ["base64-image"]
        assert payload["options"]["num_predict"] == 512
        return FakeResponse({"response": '{"action":"click"}'})

    monkeypatch.setattr(gemma.urllib.request, "urlopen", fake_urlopen)

    assert gemma.call_gemma_vision("look", "base64-image") == '{"action":"click"}'
    assert requests[0][1] == 20


def test_call_gemma_vision_json_parses_fenced_json(monkeypatch):
    monkeypatch.setattr(
        gemma,
        "call_gemma_vision",
        lambda prompt, image_b64, system="": '```json\n{"action": "done"}\n```',
    )

    assert gemma.call_gemma_vision_json("look", "base64-image") == {"action": "done"}


def test_call_gemma_json_raises_after_parse_retries(monkeypatch):
    monkeypatch.setattr(gemma, "call_gemma", lambda prompt, system="", **kwargs: "not json")

    with pytest.raises(ValueError, match="Gemma returned non-JSON"):
        gemma.call_gemma_json("open chrome", retries=1)
