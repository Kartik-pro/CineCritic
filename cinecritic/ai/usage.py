"""Token accounting and cost estimates.

Token counts come from LangChain's standard `usage_metadata` when the provider reports it, and are
otherwise left as None (never guessed). Prices come only from the user's own configuration.
"""
from __future__ import annotations

import threading
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


class UsageCollector(BaseCallbackHandler):
    """LangChain callback that sums the tokens reported by every model call it sees."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None

    def _add(self, inp: Any, out: Any) -> None:
        with self._lock:
            if isinstance(inp, int):
                self.input_tokens = (self.input_tokens or 0) + inp
            if isinstance(out, int):
                self.output_tokens = (self.output_tokens or 0) + out

    def on_llm_end(self, response, **kwargs) -> None:  # noqa: D401 (LangChain hook)
        try:
            found = False
            for generations in getattr(response, "generations", None) or []:
                for gen in generations:
                    usage = getattr(getattr(gen, "message", None), "usage_metadata", None)
                    if isinstance(usage, dict) and ("input_tokens" in usage or "output_tokens" in usage):
                        self._add(usage.get("input_tokens"), usage.get("output_tokens"))
                        found = True
            if not found:
                legacy = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
                self._add(legacy.get("prompt_tokens"), legacy.get("completion_tokens"))
        except Exception:  # accounting must never break a request
            pass


def estimate_cost(in_tokens: int | None, out_tokens: int | None, price: dict | None) -> float | None:
    """USD estimate from user-configured per-1M-token prices; None when anything is unknown."""
    if not price or in_tokens is None or out_tokens is None:
        return None
    if not (price.get("in") or price.get("out")):
        return None
    return (in_tokens * float(price.get("in", 0)) + out_tokens * float(price.get("out", 0))) / 1_000_000


def price_key(provider: str, model: str) -> str:
    return f"{provider}:{model}"
