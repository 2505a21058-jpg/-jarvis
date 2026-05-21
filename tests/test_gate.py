from agent.intent.classifier import classify
from agent.intent.router import route
from agent.intent.schema import IntentName


def test_open_app():
    intent = classify("open chrome")
    assert intent.name == IntentName.OPEN_APP
    assert intent.get("app") == "chrome"


def test_system_check():
    intent = classify("check hows my system")
    assert intent.name == IntentName.SYSTEM_CHECK


def test_system_check_cpu():
    intent = classify("whats my cpu usage")
    assert intent.name == IntentName.SYSTEM_CHECK


def test_open_and_search():
    intent = classify("open youtube and search for telugu songs")
    skill_name, params = route(intent)

    assert intent.name == IntentName.COMPUTER_USE
    assert skill_name == "computer_control"
    assert "youtube" in intent.get("goal")
    assert "telugu songs" in intent.get("goal")
    assert params["task"] == intent.get("goal")


def test_acknowledgement():
    for phrase in ["ntg", "ok", "thanks", "cool", "nah"]:
        intent = classify(phrase)
        assert intent.name == IntentName.ACKNOWLEDGEMENT, f"Failed for: {phrase}"


def test_greeting():
    intent = classify("hi")
    assert intent.name == IntentName.GREETING


def test_open_and_play():
    intent = classify("open youtube, search telugu songs and play the first song")
    assert intent.name == IntentName.OPEN_AND_PLAY


def test_compose_email():
    intent = classify("send email to john@example.com about the meeting")
    assert intent.name == IntentName.COMPOSE_EMAIL
    assert "john@example.com" in intent.get("to")


def test_reminder():
    intent = classify("remind me in 5 minutes to check my code")
    assert intent.name == IntentName.SET_REMINDER


def test_web_summary():
    intent = classify("summarise everything about tamilnadu cm")
    assert intent.name == IntentName.WEB_SUMMARY


def test_chat_not_misrouted():
    intent = classify("what is machine learning")
    assert intent.name in (IntentName.CHAT, IntentName.WEB_SUMMARY)


def test_gui_click_uses_rules_without_llm(monkeypatch):
    monkeypatch.setattr(
        "agent.intent.classifier.classify_with_llm",
        lambda raw: (_ for _ in ()).throw(AssertionError("LLM should not classify GUI clicks")),
    )

    intent = classify("click the search button")
    skill_name, params = route(intent)

    assert intent.name == IntentName.GUI_CLICK
    assert intent.classification_source == "rule"
    assert intent.get("element") == "search"
    assert skill_name == "gui_automate"
    assert params["action"] == "click"


def test_gui_type_uses_rules_without_llm(monkeypatch):
    monkeypatch.setattr(
        "agent.intent.classifier.classify_with_llm",
        lambda raw: (_ for _ in ()).throw(AssertionError("LLM should not classify GUI typing")),
    )

    intent = classify("type hello world")
    skill_name, params = route(intent)

    assert intent.name == IntentName.GUI_TYPE
    assert intent.classification_source == "rule"
    assert intent.get("text") == "hello world"
    assert skill_name == "gui_automate"
    assert params["action"] == "type_active"
