import logging

from cinecritic.errors import (
    AppError, ErrorCategory as C, HTTPFailure, InvalidInputError, RedactingFilter, classify, friendly_error, redact,
)

KEY = "SECRETKEY99XYZ"


def cat(exc, **kw):
    return classify(exc, **kw)


def test_redaction_literal_and_patterns():
    assert KEY not in redact(f"bad key {KEY}", [KEY])
    assert "AIzaSyA1234567890abcdefghijklmn" not in redact("x AIzaSyA1234567890abcdefghijklmn y")
    assert "abcdef123456" not in redact("GET /search?api_key=abcdef123456&query=x")
    assert "abcdefghijklmnop" not in redact("Authorization: Bearer abcdefghijklmnop")


def test_auth_is_permanent_and_never_leaks():
    err = cat(RuntimeError(f"401 API key not valid: {KEY}"), source="ai", secrets=[KEY], provider_label="Gemini")
    assert err.category is C.AUTH and not err.retryable
    assert KEY not in err.message and KEY not in err.technical
    assert "AI Control Center" in err.message


def test_tmdb_auth_and_not_found():
    assert cat(HTTPFailure(401), source="tmdb").category is C.AUTH
    nf = cat(HTTPFailure(404), source="tmdb")
    assert nf.category is C.TMDB and not nf.retryable


def test_transient_errors_are_retryable():
    rl = cat(HTTPFailure(429, retry_after=3), source="tmdb")
    assert rl.category is C.RATE_LIMIT and rl.retryable and rl.retry_after == 3
    assert cat(TimeoutError("timed out"), source="ai").category is C.TIMEOUT
    assert cat(ConnectionError("connection reset"), source="ai").category is C.NETWORK
    server = cat(HTTPFailure(503), source="tmdb")
    assert server.category is C.TMDB and server.retryable
    assert cat(RuntimeError("503 service unavailable"), source="ai").category is C.PROVIDER


def test_model_and_malformed():
    model = cat(RuntimeError("404 models/gemini-1.0-pro is not found or deprecated"), source="ai")
    assert model.category is C.MODEL and not model.retryable
    bad = cat(RuntimeError("1 validation error for Critique"), source="ai")
    assert bad.category is C.MALFORMED and bad.retryable


def test_internal_errors_are_classified_not_swallowed():
    err = cat(ZeroDivisionError("boom"), stage="process")   # also logged server-side with traceback
    assert err.category is C.INTERNAL and err.stage == "process" and not err.retryable
    assert "ZeroDivisionError" in err.message and "boom" in err.message      # reason is visible
    leaky = cat(AttributeError(f"bad api_key={KEY}"), secrets=[KEY])
    assert KEY not in leaky.message and KEY not in leaky.technical


def test_invalid_input_is_a_value_error():
    err = InvalidInputError("Enter a movie name first.")
    assert isinstance(err, ValueError) and isinstance(err, AppError) and err.category is C.INVALID_INPUT


def test_friendly_error_back_compat_and_filter():
    assert "AI Control Center" in friendly_error(RuntimeError("401 unauthorized"), [])
    rec = logging.LogRecord("x", logging.INFO, "f", 1, "request failed api_key=%s", ("abcdef123456789",), None)
    RedactingFilter().filter(rec)
    assert "abcdef123456789" not in rec.getMessage()
