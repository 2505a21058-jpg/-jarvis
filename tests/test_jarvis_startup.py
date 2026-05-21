from __future__ import annotations

import jarvis


class FakeMemory:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def retrieve(self, query, mode="fast", limit=None):
        self.calls.append((query, mode, limit))
        return self.responses.get(query, [])


def test_select_best_model_prefers_qwen_models_before_llama():
    assert jarvis._select_best_model(["llama3.2:3b", "qwen3:8b"]) == "qwen3:8b"
    assert jarvis._select_best_model(["qwen3:14b", "qwen3:8b"]) == "qwen3:8b"
    assert jarvis._select_best_model(["mistral:latest", "qwen3:14b"]) == "qwen3:14b"
    assert jarvis._select_best_model(["llama3.2:3b"]) == "llama3.2:3b"


def test_select_best_model_falls_back_to_llama_when_none_available():
    assert jarvis._select_best_model([]) == "llama3.2:3b"


def test_configure_default_model_env_sets_new_model_defaults(monkeypatch):
    monkeypatch.delenv("JARVIS_MODEL", raising=False)
    monkeypatch.delenv("JARVIS_ACTION_MODEL", raising=False)
    monkeypatch.delenv("JARVIS_EMBED_MODEL", raising=False)

    jarvis._configure_default_model_env()

    assert jarvis.os.environ["JARVIS_MODEL"] == "qwen3:8b"
    assert jarvis.os.environ["JARVIS_ACTION_MODEL"] == "gemma3:4b"
    assert jarvis.os.environ["JARVIS_EMBED_MODEL"] == "nomic-embed-text"


def test_model_manager_preference_order_uses_available_qwen3_first():
    import model_manager

    assert model_manager.PREFERRED_MODELS == [
        "qwen3:8b",
        "qwen3:14b",
        "mistral:latest",
        "llama3.2:3b",
        "llama3.2:latest",
        "jarvis-core:latest",
    ]
    assert model_manager.select_best_model(["llama3.2:3b", "qwen3:8b"]) == "qwen3:8b"


def test_print_startup_readiness_shows_model_roles(capsys):
    not_configured = jarvis._print_startup_readiness(
        ollama_models=["gemma3:4b", "qwen3:8b", "nomic-embed-text:latest"],
        active_model="qwen3:8b",
        memory_count=972,
        semantic_memory_ok=True,
        remote_bridge_enabled=False,
        bridge_token_set=False,
        telegram_token_set=False,
        websockets_ok=True,
        playwright_ok=True,
        hero_ok=False,
        hero_detail="Not available",
        chrome_ready=True,
        chrome_profile="Profile 3",
        psutil_ok=True,
        pdfplumber_ok=True,
        smtp_set=False,
        llava_ok=False,
        mss_ok=True,
        rawvision_elements=35,
        rawvision_layers=["process_monitor", "uia"],
        rawvision_ms=1719.0,
        hands_ok=True,
    )

    output = capsys.readouterr().out
    assert "[MODELS]" in output
    assert "[OK] Main model          qwen3:8b" in output
    assert "[OK] Action model        gemma3:4b  (automation + vision)" in output
    assert "[OK] Embed model         nomic-embed-text" in output
    assert "[OK] Chrome harness      Port 9222 ready  |  Profile: Profile 3" in output
    assert "[OK] Gemma3 vision       gemma3:4b  (computer use decisions)" in output
    assert not_configured == 0


def test_profile_name_returns_empty_when_name_not_found():
    memory = FakeMemory({"user profile name": []})

    assert jarvis._profile_name(memory) == ""


def test_profile_name_extracts_name_from_retrieved_content():
    memory = FakeMemory(
        {"user profile name": [{"content": "My name is Shiva and I use Jarvis."}]}
    )

    assert jarvis._profile_name(memory) == "Shiva"


def test_profile_name_reads_profile_dict_fallback():
    memory = FakeMemory(
        {
            "user profile name": [{"content": "No explicit name here."}],
            "profile": [{"profile": {"name": "Shiva"}}],
        }
    )

    assert jarvis._profile_name(memory) == "Shiva"
