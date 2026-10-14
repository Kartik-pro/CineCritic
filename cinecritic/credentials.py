"""Credential status and bounded connection tests (UI-independent; stores no secrets)."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from .ai.providers import ModelRef, build_llm
from .config import PROVIDERS, Provider
from .errors import AppError, ErrorCategory
from .metadata import check_connection
from .pipeline import call_with_retries

SERVICES: tuple[str, ...] = (*PROVIDERS, "TMDB")

NOT_CONFIGURED, CONFIGURED, VALID, INVALID, FAILED = (
    "Not configured", "Configured", "Valid", "Invalid", "Connection failed",
)
_CSS = {NOT_CONFIGURED: "no", CONFIGURED: "mid", VALID: "ok", INVALID: "no", FAILED: "warn"}


@dataclass(frozen=True)
class StatusRecord:
    fp: str                  # fingerprint of (service, model, key): a changed key/model invalidates the result
    state: str               # 'valid' | 'invalid' | 'failed'
    message: str
    category: str = ""
    latency_ms: int | None = None
    checked_at: float = 0.0
    rate_limited: bool = False
    quota: bool = False


def fingerprint(service: str, model: str, key: str) -> str:
    return hashlib.sha256(f"{service}|{model}|{key}".encode()).hexdigest()[:12]


def mask(key: str) -> str:
    return f"••••{key[-4:]}" if len(key) >= 8 else "••••"


def status_label(service: str, model: str, key: str, record: StatusRecord | None) -> tuple[str, str]:
    """Return (label, css-class) for a service."""
    if not key:
        return NOT_CONFIGURED, _CSS[NOT_CONFIGURED]
    if record and record.fp == fingerprint(service, model, key):
        label = {"valid": VALID, "invalid": INVALID, "failed": FAILED}[record.state]
        return label, _CSS[label]
    return CONFIGURED, _CSS[CONFIGURED]


def _record(service: str, model: str, key: str, err: AppError | None, latency_ms: int | None,
            message: str = "Connection successful.") -> StatusRecord:
    fp, now = fingerprint(service, model, key), time.time()
    if err is None:
        return StatusRecord(fp, "valid", message, latency_ms=latency_ms, checked_at=now)
    permanent = err.category in (ErrorCategory.AUTH, ErrorCategory.MODEL, ErrorCategory.INVALID_INPUT)
    low = f"{err.technical} {err.message}".lower()
    return StatusRecord(fp, "invalid" if permanent else "failed", err.message, err.category.value, latency_ms, now,
                        rate_limited=err.category is ErrorCategory.RATE_LIMIT,
                        quota=err.category is ErrorCategory.RATE_LIMIT and ("quota" in low or "exhausted" in low))


def preflight_error(service: str, model: str, key: str, record: StatusRecord | None) -> AppError | None:
    """Fail fast if this exact key+model already failed its connection test (pure, thread-safe)."""
    if record and key and record.fp == fingerprint(service, model, key) and record.state == "invalid":
        try:
            category = ErrorCategory(record.category or "auth")
        except ValueError:
            category = ErrorCategory.AUTH
        return AppError(category, record.message, source="ai")
    return None


def check_ai(provider: Provider, model: str, key: str, builder=build_llm) -> StatusRecord:
    """One tiny request that validates the key AND the model ID, and measures latency."""
    model = (model or "").strip() or provider.default_model
    started = time.perf_counter()
    try:
        def probe():
            builder(ModelRef(provider.label, model), key).invoke("Reply with the single word OK.")

        call_with_retries(probe, stage="test", source="ai", secrets=[key], provider_label=provider.label,
                          max_attempts=2)
        latency = int((time.perf_counter() - started) * 1000)
        return _record(provider.label, model, key, None, latency, f"Connected. {model} responded in {latency} ms.")
    except AppError as err:
        return _record(provider.label, model, key, err, int((time.perf_counter() - started) * 1000))


def check_tmdb(key: str) -> StatusRecord:
    started = time.perf_counter()
    try:
        call_with_retries(lambda: check_connection(key), stage="test", source="tmdb", secrets=[key], max_attempts=2)
        return _record("TMDB", "", key, None, int((time.perf_counter() - started) * 1000))
    except AppError as err:
        return _record("TMDB", "", key, err, int((time.perf_counter() - started) * 1000))
