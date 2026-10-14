"""Centralised error model: categories, classification, redaction and server logging.

Every failure in the app (TMDB, AI provider, network, input, internal bugs) is turned
into an `AppError` with a category, a safe user-facing message and a `retryable` flag.
Nothing here ever includes an API key: known secrets are replaced literally and common
credential patterns are scrubbed from every message and log line.
"""
from __future__ import annotations

import logging
import os
import re
from enum import Enum
from typing import Iterable

logger = logging.getLogger("cinecritic")


class ErrorCategory(str, Enum):
    TMDB = "tmdb"
    PROVIDER = "provider"
    AUTH = "auth"
    NETWORK = "network"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    INVALID_INPUT = "invalid_input"
    MODEL = "model"
    MALFORMED = "malformed_response"
    BUDGET = "budget"
    INTERNAL = "internal"


CATEGORY_LABELS = {
    ErrorCategory.TMDB: "TMDB",
    ErrorCategory.PROVIDER: "AI provider",
    ErrorCategory.AUTH: "Authentication",
    ErrorCategory.NETWORK: "Network",
    ErrorCategory.TIMEOUT: "Timeout",
    ErrorCategory.RATE_LIMIT: "Rate limit",
    ErrorCategory.INVALID_INPUT: "Invalid input",
    ErrorCategory.MODEL: "Model",
    ErrorCategory.MALFORMED: "Malformed response",
    ErrorCategory.BUDGET: "Budget limit",
    ErrorCategory.INTERNAL: "Internal error",
}

# --------------------------------------------------------------------------- redaction
_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|token|authorization|x-api-key)\b\s*[=:]\s*(?:bearer\s+)?[^\s&\"',;]{6,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{10,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\beyJ[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{4,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
]


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Replace known secrets literally, then scrub anything that looks like a credential."""
    text = str(text)
    for secret in secrets:
        if secret and len(secret) >= 6:
            text = text.replace(secret, "[redacted]")
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: f"{m.group(1)}=[redacted]", text)
        else:
            text = pattern.sub("[redacted]", text)
    return text


class RedactingFilter(logging.Filter):
    """Last line of defence: scrub every record that reaches a handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def configure_logging() -> None:
    """Idempotent server-side logging setup (Streamlit re-runs the script constantly)."""
    if getattr(logger, "_cinecritic_configured", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    logger.setLevel(os.getenv("CINECRITIC_LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    logger._cinecritic_configured = True  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- error types
class AppError(Exception):
    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        *,
        retryable: bool = False,
        stage: str = "",
        source: str = "",
        status: int | None = None,
        technical: str = "",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.retryable = retryable
        self.stage = stage
        self.source = source
        self.status = status
        self.technical = technical or message
        self.retry_after = retry_after

    def __str__(self) -> str:
        return self.message


class InvalidInputError(AppError, ValueError):
    def __init__(self, message: str, stage: str = "search") -> None:
        AppError.__init__(self, ErrorCategory.INVALID_INPUT, message, stage=stage)


class MissingAPIKeyError(AppError):
    def __init__(self, label: str) -> None:
        super().__init__(
            ErrorCategory.AUTH,
            f"No {label} API key is configured. Open AI Control Center → API Keys and add one.",
            source="ai",
        )


class CritiqueError(AppError):
    def __init__(self, message: str = "The model returned an incomplete response.") -> None:
        super().__init__(ErrorCategory.MALFORMED, message + " Please try again.", retryable=True, source="ai")


class HTTPFailure(Exception):
    """Carrier for a non-2xx HTTP response (so classification never sees the URL or key)."""

    def __init__(self, status_code: int, retry_after: float | None = None) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after


# --------------------------------------------------------------------------- classification
_STATUS_RE = re.compile(r"\b(401|403|404|408|429|500|502|503|504)\b")
_AUTH = ("api key not valid", "api_key_invalid", "invalid api key", "incorrect api key",
         "invalid_api_key", "unauthorized", "authentication", "permission denied",
         "permission_denied", "invalid x-api-key", "api key expired", "invalid token")
_MODEL = ("not found", "not supported", "deprecated", "does not exist", "unsupported",
          "invalid model", "unknown model", "no longer available", "decommissioned")
_RATE = ("429", "quota", "rate limit", "rate_limit", "resource_exhausted", "too many requests")
_TIMEOUT = ("timeout", "timed out", "deadline exceeded")
_NETWORK = ("connection", "name resolution", "dns", "ssl", "unreachable", "network")
_SERVER = ("overloaded", "service unavailable", "internal server error", "bad gateway",
           "temporarily unavailable", "gateway")
_MALFORMED = ("validation error", "outputparser", "failed to parse", "nonetype",
              "jsondecode", "expecting value", "could not parse")


def _status_of(exc: Exception, low: str) -> int | None:
    for candidate in (
        getattr(exc, "status_code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
        getattr(exc, "code", None),
    ):
        if isinstance(candidate, int) and 100 <= candidate <= 599:
            return candidate
    match = _STATUS_RE.search(low)
    return int(match.group(1)) if match else None


def _retry_after(exc: Exception) -> float | None:
    value = getattr(exc, "retry_after", None)
    if value is None:
        headers = getattr(getattr(exc, "response", None), "headers", None) or {}
        value = headers.get("Retry-After") if hasattr(headers, "get") else None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def classify(
    exc: BaseException,
    *,
    stage: str = "",
    source: str = "",           # "tmdb" | "ai" | ""
    secrets: Iterable[str] = (),
    provider_label: str = "",
) -> AppError:
    """Map any exception to an AppError with a safe message. Unexpected ones are logged."""
    if isinstance(exc, AppError):
        if stage and not exc.stage:
            exc.stage = stage
        return exc

    secrets = list(secrets)
    name = type(exc).__name__
    text = redact(f"{name}: {exc}", secrets)
    low = text.lower()
    status = _status_of(exc, low)  # type: ignore[arg-type]
    who = "TMDB" if source == "tmdb" else (provider_label or "The AI provider")
    retry_after = _retry_after(exc)  # type: ignore[arg-type]
    tech = text[:300]

    def make(category, message, retryable=False):
        return AppError(category, message, retryable=retryable, stage=stage, source=source,
                        status=status, technical=tech, retry_after=retry_after)

    if status in (401, 403) or any(k in low for k in _AUTH):
        if source == "tmdb":
            return make(ErrorCategory.AUTH, "TMDB rejected the key. Open AI Control Center and check it "
                        "(use the v3 API key or the v4 read-access token).")
        return make(ErrorCategory.AUTH, f"{who} rejected your API key. Open AI Control Center, update "
                    "the key, then press Test connection.")
    if source == "tmdb" and status == 404:
        return make(ErrorCategory.TMDB, "TMDB could not find that title.")
    if source != "tmdb" and ((status == 404) or ("model" in low and any(k in low for k in _MODEL))):
        return make(ErrorCategory.MODEL, "That model ID is unavailable or deprecated for your key. "
                    "Pick another model in AI Control Center.")
    if status == 429 or any(k in low for k in _RATE):
        wait = f" Try again in about {int(retry_after)}s." if retry_after else ""
        return make(ErrorCategory.RATE_LIMIT, f"{who} rate limit or quota reached.{wait} "
                    "Wait a moment, or switch key or model in AI Control Center.", retryable=True)
    if isinstance(exc, TimeoutError) or "timeout" in name.lower() or any(k in low for k in _TIMEOUT) or status == 408:
        return make(ErrorCategory.TIMEOUT, f"{who} took too long to respond. Retry in a moment.", retryable=True)
    if "connectionerror" in name.lower() or "connecterror" in name.lower() or any(k in low for k in _NETWORK):
        return make(ErrorCategory.NETWORK, "Network problem reaching "
                    f"{'TMDB' if source == 'tmdb' else 'the provider'}. Check your connection and retry.",
                    retryable=True)
    if (status is not None and status >= 500) or any(k in low for k in _SERVER):
        category = ErrorCategory.TMDB if source == "tmdb" else ErrorCategory.PROVIDER
        return make(category, f"{who} is temporarily unavailable. Retry shortly.", retryable=True)
    if name in ("ValidationError", "OutputParserException", "CritiqueError", "JSONDecodeError") or any(k in low for k in _MALFORMED):
        return make(ErrorCategory.MALFORMED, "The model returned an incomplete response. Please try again.", retryable=True)

    logger.error("unclassified %s in stage=%s source=%s: %s", name, stage or "-", source or "-", tech, exc_info=exc)
    detail = redact(str(exc), secrets).strip().replace("\n", " ")[:160]
    return make(ErrorCategory.INTERNAL, f"Unexpected error ({name}: {detail}). The full traceback was "
                "logged on the server; copy the diagnostics if you need to report it.")


def friendly_error(exc: BaseException, secrets: Iterable[str] = ()) -> str:
    """Back-compat helper: just the safe user message."""
    return classify(exc, secrets=secrets).message
