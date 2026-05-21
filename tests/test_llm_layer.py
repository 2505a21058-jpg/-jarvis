from __future__ import annotations

from models import llm


def test_model_manager_disables_qwen3_thinking(monkeypatch):
    import model_manager

    calls = []

    class FakeOllama:
        def chat(self, **kwargs):
            calls.append(kwargs)
            return {"message": {"content": "hello"}}

    monkeypatch.setattr(model_manager, "_get_ollama", lambda: FakeOllama())

    response = model_manager.model_manager.ollama_chat(
        "qwen3:8b",
        [{"role": "user", "content": "hello"}],
        options={"num_predict": 10},
    )

    assert response["message"]["content"] == "hello"
    assert calls[0]["think"] is False


def test_get_active_model_defaults_to_qwen3_when_detection_fails(monkeypatch):
    monkeypatch.delenv("JARVIS_MODEL", raising=False)
    monkeypatch.setattr(
        "models.model_manager.get_best_available_model",
        lambda: (_ for _ in ()).throw(RuntimeError("ollama unavailable")),
    )

    assert llm._get_active_model() == "qwen3:8b"


def test_call_llm_cached_reuses_identical_completion(monkeypatch):
    calls = []

    def fake_call_llm(**kwargs):
        calls.append(kwargs)
        return "cached-response"

    llm._cached_completion.cache_clear()
    monkeypatch.setattr(llm, "call_llm", fake_call_llm)

    first = llm.call_llm_cached("classifier", "system", "user", temperature=0.0, max_tokens=20)
    second = llm.call_llm_cached("classifier", "system", "user", temperature=0.0, max_tokens=20)

    assert first == "cached-response"
    assert second == "cached-response"
    assert len(calls) == 1


def test_call_llm_cached_keys_on_system_key(monkeypatch):
    calls = []

    def fake_call_llm(**kwargs):
        calls.append(kwargs)
        return f"response-{len(calls)}"

    llm._cached_completion.cache_clear()
    monkeypatch.setattr(llm, "call_llm", fake_call_llm)

    first = llm.call_llm_cached("intent", "system", "user")
    second = llm.call_llm_cached("planner", "system", "user")

    assert first == "response-1"
    assert second == "response-2"
    assert len(calls) == 2


def test_call_llm_json_retries_and_parses_fenced_json(monkeypatch):
    responses = iter(["not json", "```json\n{\"ok\": true}\n```"])

    monkeypatch.setattr(llm, "call_llm", lambda **kwargs: next(responses))
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)

    assert llm.call_llm_json("system", "user", retries=1) == {"ok": True}


def test_load_prompt_template_uses_fallback_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    llm._PROMPT_CACHE.clear()

    assert llm.load_prompt_template("missing", "fallback") == "fallback"


def test_load_prompt_template_reads_prompt_file(tmp_path, monkeypatch):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "planner.txt").write_text("from-file", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    llm._PROMPT_CACHE.clear()

    assert llm.load_prompt_template("planner", "fallback") == "from-file"
