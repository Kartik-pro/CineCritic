"""LLM construction with per-key caching."""
from __future__ import annotations

from functools import lru_cache

from langchain.chat_models import init_chat_model

from .config import Provider
from .env_manager import get_api_key


class MissingAPIKeyError(RuntimeError):
    """Raised when the selected provider has no API key configured."""


@lru_cache(maxsize=8)
def _build(prefix: str, model_name: str, api_key: str):
    # api_key is part of the cache key, so changing the key rebuilds the model.
    return init_chat_model(f"{prefix}:{model_name}")


def get_llm(provider: Provider, model_name: str):
    key = get_api_key(provider.env_var)
    if not key:
        raise MissingAPIKeyError(f"Add your {provider.env_var} in the sidebar first.")
    return _build(provider.prefix, model_name.strip() or provider.default_model, key)
