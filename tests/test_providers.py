import pytest

from cinecritic.ai import providers
from cinecritic.ai.providers import ModelRef, build_llm, discover_models, package_available, resolve_key
from cinecritic.config import PROVIDERS
from cinecritic.errors import AppError


class Resp:
    def __init__(self, status, payload):
        self.status_code, self._p, self.headers = status, payload, {}

    def json(self):
        return self._p


def fake_get(monkeypatch, status, payload, seen=None):
    def get(url, headers=None, params=None, timeout=None):
        if seen is not None:
            seen.append((url, dict(headers or {}), params))
        return Resp(status, payload)
    monkeypatch.setattr(providers.requests, "get", get)


def test_gemini_discovery_parses_limits_and_methods_and_keeps_key_in_header(monkeypatch):
    seen = []
    fake_get(monkeypatch, 200, {"models": [
        {"name": "models/gemini-a", "displayName": "A", "inputTokenLimit": 1000, "outputTokenLimit": 10,
         "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/embed-x", "supportedGenerationMethods": ["embedContent"]}]}, seen)
    r = discover_models("Gemini", "SECRETKEY")
    assert r.ok and [m.id for m in r.models] == ["embed-x", "gemini-a"]
    a = next(m for m in r.models if m.id == "gemini-a")
    assert a.input_limit == 1000 and a.chat is True and next(m for m in r.models if m.id == "embed-x").chat is False
    url, headers, params = seen[0]
    assert "SECRETKEY" not in url and "SECRETKEY" not in str(params) and headers["x-goog-api-key"] == "SECRETKEY"


def test_openai_filters_non_chat_names_and_flags_unverified(monkeypatch):
    fake_get(monkeypatch, 200, {"data": [{"id": "gpt-4o"}, {"id": "text-embedding-3"}, {"id": "whisper-1"}]})
    r = discover_models("OpenAI", "k")
    assert [m.id for m in r.models] == ["gpt-4o"] and r.models[0].chat is None and "unverified" in r.models[0].source


def test_anthropic_and_mistral_report_what_the_provider_returns(monkeypatch):
    fake_get(monkeypatch, 200, {"data": [{"id": "claude-x", "display_name": "X", "max_input_tokens": 200000}]})
    assert discover_models("Anthropic", "k").models[0].input_limit == 200000
    fake_get(monkeypatch, 200, {"data": [{"id": "mistral-l", "max_context_length": 32000,
                                           "capabilities": {"completion_chat": True, "vision": False}}]})
    m = discover_models("Mistral", "k").models[0]
    assert m.input_limit == 32000 and m.chat is True and m.vision is False


def test_discovery_failures_never_raise_and_never_leak(monkeypatch):
    fake_get(monkeypatch, 401, {})
    r = discover_models("Gemini", "SECRETKEY")
    assert not r.ok and "SECRETKEY" not in r.error and "key" in r.error.lower()
    assert "not supported" in discover_models("Nope", "k").error
    assert "No API key" in discover_models("Gemini", "").error
    fake_get(monkeypatch, 200, {"models": []})
    assert "no models" in discover_models("Gemini", "k").error.lower()

    def boom(*a, **k):
        raise providers.requests.ConnectionError("failed api_key=SECRETKEY")
    monkeypatch.setattr(providers.requests, "get", boom)
    assert "SECRETKEY" not in discover_models("Gemini", "SECRETKEY").error


def test_resolve_key_prefers_session_then_server(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "from-env")
    g = PROVIDERS["Gemini"]
    assert resolve_key(g, {"Gemini": " typed "}) == ("typed", "session")
    assert resolve_key(g, {}) == ("from-env", "secrets/env")
    monkeypatch.delenv("GOOGLE_API_KEY")
    assert resolve_key(g, {}) == ("", "")


def test_build_llm_validates_inputs_and_missing_package(monkeypatch):
    with pytest.raises(AppError):
        build_llm(ModelRef("Nope", "m"), "k")
    with pytest.raises(AppError) as info:
        build_llm(ModelRef("Gemini", "m"), "")
    assert "API key" in info.value.message
    monkeypatch.setattr(providers, "package_available", lambda p: False)
    with pytest.raises(AppError) as info:
        build_llm(ModelRef("OpenAI", "m"), "k")
    assert "langchain-openai" in info.value.message


def test_build_llm_passes_settings_to_langchain(monkeypatch):
    import langchain.chat_models as cm
    captured = {}
    monkeypatch.setattr(cm, "init_chat_model", lambda model, **kw: captured.update(model=model, **kw) or "llm")
    monkeypatch.setattr(providers, "package_available", lambda p: True)
    assert build_llm(ModelRef("Anthropic", ""), "k", temperature=0.2, timeout=33) == "llm"
    assert captured["model"] == PROVIDERS["Anthropic"].default_model and captured["max_tokens"] == 4096
    assert captured["temperature"] == 0.2 and captured["timeout"] == 33 and captured["max_retries"] == 0
    build_llm(ModelRef("Gemini", "g"), "k", max_tokens=500)
    assert captured["max_tokens"] == 500 and captured["model_provider"] == "google_genai"
