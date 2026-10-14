import pytest

from cinecritic import credentials
from cinecritic.config import PROVIDERS
from cinecritic.credentials import (
    CONFIGURED, FAILED, INVALID, NOT_CONFIGURED, VALID, StatusRecord, check_ai, check_tmdb, fingerprint, mask,
    preflight_error, status_label,
)
from cinecritic.errors import AppError, ErrorCategory as C, HTTPFailure

GEMINI = PROVIDERS["Gemini"]
KEY = "AIzaSyFAKEKEY1234567890abcdefghij"


def test_status_labels_follow_key_and_test_result():
    assert status_label("Gemini", "m", "", None)[0] == NOT_CONFIGURED
    assert status_label("Gemini", "m", KEY, None)[0] == CONFIGURED
    ok = StatusRecord(fingerprint("Gemini", "m", KEY), "valid", "ok")
    assert status_label("Gemini", "m", KEY, ok)[0] == VALID
    # changing the key or the model invalidates the earlier test result
    assert status_label("Gemini", "m", KEY + "x", ok)[0] == CONFIGURED
    assert status_label("Gemini", "other-model", KEY, ok)[0] == CONFIGURED
    bad = StatusRecord(fingerprint("Gemini", "m", KEY), "invalid", "no")
    assert status_label("Gemini", "m", KEY, bad)[0] == INVALID
    assert status_label("Gemini", "m", KEY, StatusRecord(bad.fp, "failed", "net"))[0] == FAILED


def test_mask_never_reveals_more_than_last_four():
    assert mask(KEY) == "••••ghij" and KEY not in mask(KEY) and mask("abc") == "••••"


class _OkLLM:
    def invoke(self, prompt):
        return "OK"


def _builder(llm):
    return lambda ref, key, **kw: llm


def test_check_ai_valid(monkeypatch):
    rec = check_ai(GEMINI, "gemini-x", KEY, builder=_builder(_OkLLM()))
    assert rec.state == "valid" and "gemini-x" in rec.message and rec.fp == fingerprint("Gemini", "gemini-x", KEY)


def test_check_ai_invalid_key_and_unknown_model_are_invalid_not_retried(monkeypatch):
    calls = {"n": 0}

    def make(msg):
        class Bad:
            def invoke(self, prompt):
                calls["n"] += 1
                raise RuntimeError(msg)
        return Bad()

    rec = check_ai(GEMINI, "m", KEY, builder=_builder(make(f"401 API key not valid {KEY}")))
    assert rec.state == "invalid" and rec.category == "auth" and KEY not in rec.message and calls["n"] == 1

    assert check_ai(GEMINI, "m", KEY, builder=_builder(make("404 model gemini-1 is not found"))).category == "model"


def test_check_ai_network_problem_is_connection_failed(monkeypatch):
    from cinecritic import pipeline
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)

    class Down:
        def invoke(self, prompt):
            raise TimeoutError("timed out")

    assert check_ai(GEMINI, "m", KEY, builder=_builder(Down())).state == "failed"


def test_check_tmdb_states(monkeypatch):
    from cinecritic import pipeline
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    monkeypatch.setattr(credentials, "check_connection", lambda key: None)
    assert check_tmdb("k" * 32).state == "valid"

    def deny(key):
        raise AppError(C.AUTH, "TMDB rejected the key.")

    monkeypatch.setattr(credentials, "check_connection", deny)
    assert check_tmdb("k" * 32).state == "invalid"


def test_check_ai_records_latency_and_rate_limit_flags(monkeypatch):
    from cinecritic import pipeline
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    ok = check_ai(GEMINI, "m", KEY, builder=_builder(_OkLLM()))
    assert ok.latency_ms is not None and ok.checked_at > 0

    class Quota:
        def invoke(self, prompt):
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")

    rec = check_ai(GEMINI, "m", KEY, builder=_builder(Quota()))
    assert rec.state == "failed" and rec.rate_limited and rec.quota
