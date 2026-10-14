"""Provider adapters: key resolution, LangChain model construction and model discovery.

Provider-specific details live here and nowhere else. Discovery uses each provider's documented
"list models" endpoint through plain HTTPS. Keys are sent only in request headers, and failures
are classified (never re-raised as raw requests errors, whose text could carry credentials).
"""
from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass, field

import requests

from ..config import PROVIDERS, REQUEST_TIMEOUT_S, Provider
from ..env_manager import get_server_key
from ..errors import AppError, ErrorCategory, HTTPFailure, MissingAPIKeyError, classify

DISCOVERY_TIMEOUT_S = 12


@dataclass(frozen=True)
class ModelRef:
    provider: str
    model: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True)
class ModelInfo:
    id: str
    display: str = ""
    input_limit: int | None = None      # provider-reported context window, when reported
    output_limit: int | None = None
    chat: bool | None = None            # True/False only when the provider says so; None = unknown
    vision: bool | None = None
    source: str = "provider API"


@dataclass
class DiscoveryResult:
    provider: str
    models: list[ModelInfo] = field(default_factory=list)
    fetched_at: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


# --------------------------------------------------------------------------- keys + availability
def package_available(provider: Provider) -> bool:
    if not provider.package:
        return True
    try:
        return importlib.util.find_spec(provider.package) is not None
    except (ImportError, ValueError):
        return False


def resolve_key(provider: Provider, session_keys: dict[str, str]) -> tuple[str, str]:
    """Return (key, source) where source is 'session', 'secrets/env' or ''. Session wins."""
    key = (session_keys.get(provider.label) or "").strip()
    if key:
        return key, "session"
    server = get_server_key(provider.env_var)
    return (server, "secrets/env") if server else ("", "")


# --------------------------------------------------------------------------- construction
def build_llm(ref: ModelRef, api_key: str, *, temperature: float | None = None, max_tokens: int | None = None,
              timeout: float | None = None):
    """Build a chat model bound to this caller's key. Deliberately not cached (keys must not
    outlive their session); construction is cheap compared with the network call."""
    provider = PROVIDERS.get(ref.provider)
    if provider is None:
        raise AppError(ErrorCategory.INVALID_INPUT, f"Unknown provider “{ref.provider}”.")
    if not api_key:
        raise MissingAPIKeyError(provider.label)
    if not package_available(provider):
        raise AppError(ErrorCategory.PROVIDER,
                       f"{provider.label} support needs the `{provider.pip_name}` package. "
                       f"Add it to requirements.txt and redeploy.", source="ai")
    from langchain.chat_models import init_chat_model  # imported lazily: heavy, and mocked in tests

    kwargs: dict = {"model_provider": provider.prefix, "api_key": api_key,
                    "timeout": timeout or REQUEST_TIMEOUT_S, "max_retries": 0}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens:
        kwargs["max_tokens"] = int(max_tokens)
    elif provider.prefix == "anthropic":
        kwargs["max_tokens"] = 4096       # Anthropic requires an explicit output limit
    return init_chat_model((ref.model or "").strip() or provider.default_model, **kwargs)


# --------------------------------------------------------------------------- discovery
def _get_json(url: str, headers: dict, params: dict | None = None) -> dict:
    try:
        response = requests.get(url, headers=headers, params=params, timeout=DISCOVERY_TIMEOUT_S)
    except requests.RequestException as exc:
        raise classify(exc, source="ai", secrets=list(headers.values())) from None
    if response.status_code >= 400:
        raise classify(HTTPFailure(response.status_code), source="ai")
    try:
        data = response.json()
    except ValueError:
        raise AppError(ErrorCategory.MALFORMED, "The provider returned an unreadable model list.",
                       retryable=True, source="ai") from None
    return data if isinstance(data, dict) else {}


_NON_CHAT_HINTS = ("embed", "whisper", "tts", "dall-e", "moderation", "davinci", "babbage", "transcribe",
                   "image", "audio", "realtime", "search-preview")


def _int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _gemini(key: str) -> list[ModelInfo]:
    data = _get_json("https://generativelanguage.googleapis.com/v1beta/models",
                     {"x-goog-api-key": key}, {"pageSize": 200})
    out = []
    for m in data.get("models") or []:
        name = str(m.get("name", "")).removeprefix("models/")
        if not name:
            continue
        methods = m.get("supportedGenerationMethods") or []
        out.append(ModelInfo(name, m.get("displayName", ""), _int(m.get("inputTokenLimit")),
                             _int(m.get("outputTokenLimit")), chat=("generateContent" in methods) if methods else None))
    return out


def _openai(key: str) -> list[ModelInfo]:
    data = _get_json("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})
    out = []
    for m in data.get("data") or []:
        mid = str(m.get("id", ""))
        if mid and not any(h in mid.lower() for h in _NON_CHAT_HINTS):
            out.append(ModelInfo(mid, source="provider API (non-chat models filtered by name; capabilities unverified)"))
    return out


def _anthropic(key: str) -> list[ModelInfo]:
    data = _get_json("https://api.anthropic.com/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"},
                     {"limit": 100})
    out = []
    for m in data.get("data") or []:
        mid = str(m.get("id", ""))
        if mid:
            out.append(ModelInfo(mid, m.get("display_name", ""), _int(m.get("max_input_tokens")),
                                 _int(m.get("max_tokens")), chat=True))
    return out


def _mistral(key: str) -> list[ModelInfo]:
    data = _get_json("https://api.mistral.ai/v1/models", {"Authorization": f"Bearer {key}"})
    out = []
    for m in data.get("data") or []:
        mid = str(m.get("id", ""))
        caps = m.get("capabilities") or {}
        if mid:
            out.append(ModelInfo(mid, m.get("name", "") or "", _int(m.get("max_context_length")), None,
                                 chat=caps.get("completion_chat") if "completion_chat" in caps else None,
                                 vision=caps.get("vision") if "vision" in caps else None))
    return out


_DISCOVERERS = {"Gemini": _gemini, "OpenAI": _openai, "Anthropic": _anthropic, "Mistral": _mistral}


def discover_models(provider_label: str, key: str, clock=time.time) -> DiscoveryResult:
    """List the models a provider says this key can see. Never raises."""
    result = DiscoveryResult(provider_label, fetched_at=clock())
    fn = _DISCOVERERS.get(provider_label)
    if fn is None:
        result.error = "Model discovery is not supported for this provider; enter a model ID manually."
        return result
    if not key:
        result.error = "No API key configured."
        return result
    try:
        models = fn(key)
    except AppError as err:
        result.error = err.message
        return result
    except Exception as exc:  # defensive: a parser surprise must not break the page
        result.error = f"Unexpected discovery failure ({type(exc).__name__})."
        return result
    result.models = sorted(models, key=lambda m: m.id)
    if not result.models:
        result.error = "The provider returned no models for this key."
    return result
