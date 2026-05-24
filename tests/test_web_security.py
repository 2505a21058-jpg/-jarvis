from __future__ import annotations


def test_web_auth_allows_local_request_when_no_token_configured(monkeypatch):
    from interfaces.web.security import is_web_request_authorized

    monkeypatch.delenv("JARVIS_WEB_TOKEN", raising=False)

    assert is_web_request_authorized({}) is True


def test_web_auth_requires_matching_configured_token(monkeypatch):
    from interfaces.web.security import is_web_request_authorized

    monkeypatch.setenv("JARVIS_WEB_TOKEN", "secret-token")

    assert is_web_request_authorized({}) is False
    assert is_web_request_authorized({"x-jarvis-token": "wrong"}) is False
    assert is_web_request_authorized({"x-jarvis-token": "secret-token"}) is True
    assert is_web_request_authorized({"authorization": "Bearer secret-token"}) is True


def test_web_origin_check_rejects_cross_site_origins():
    from interfaces.web.security import is_safe_web_origin

    assert is_safe_web_origin("http://127.0.0.1:9090", "127.0.0.1:9090") is True
    assert is_safe_web_origin("http://localhost:9090", "127.0.0.1:9090") is True
    assert is_safe_web_origin("https://evil.example", "127.0.0.1:9090") is False
