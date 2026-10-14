from types import SimpleNamespace

import pytest

from cinecritic import pipeline
from cinecritic.ai.gateway import CircuitBreaker
from cinecritic.errors import AppError, ErrorCategory as C
from cinecritic.pipeline import PipelineRun
from tests.helpers import FakeLLM, make_gateway


def setup_function(_):
    pass


def events():
    log = []
    return log, lambda **kw: log.append(kw)


def test_missing_key_is_an_auth_error_for_prepare_and_call():
    gw = make_gateway(FakeLLM(), keys={})
    for fn in (lambda: gw.prepare("analysis"), lambda: gw.call("analysis", lambda llm, cfg: 1)):
        with pytest.raises(AppError) as info:
            fn()
        assert info.value.category is C.AUTH
    with pytest.raises(AppError):
        gw.prepare("nonsense")


def test_success_records_one_usage_event_with_lifecycle_and_tokens():
    log, record = events()
    gw = make_gateway(FakeLLM(), record=record)

    def fn(llm, cfg):
        usage = {"input_tokens": 120, "output_tokens": 30}
        gen = SimpleNamespace(message=SimpleNamespace(usage_metadata=usage))
        cfg["callbacks"][0].on_llm_end(SimpleNamespace(generations=[[gen]], llm_output=None))
        return "ok"

    run = PipelineRun("x", kind="ask")
    assert gw.call("ask", fn, run=run, stage="answer") == "ok"
    (e,) = log
    assert e["ok"] and e["task"] == "ask" and e["in_tokens"] == 120 and e["out_tokens"] == 30 and e["retries"] == 0
    assert [s["stage"] for s in e["stages"]] == ["accepted", "validated", "selected", "dispatched",
                                                  "response received", "output validated", "returned"]
    assert gw.model_used("ask").startswith("Gemini:") and e["run_id"] == run.run_id


def test_unreported_tokens_stay_unknown_not_zero():
    log, record = events()
    make_gateway(FakeLLM(), record=record).call("ask", lambda llm, cfg: "x")
    assert log[0]["in_tokens"] is None and log[0]["out_tokens"] is None


def test_transient_failures_retry_then_record_failure_without_leaking_the_key(monkeypatch):
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    log, record = events()
    gw = make_gateway(FakeLLM(), record=record, keys={"Gemini": "SECRETKEY123456"})
    calls = {"n": 0}

    def fn(llm, cfg):
        calls["n"] += 1
        raise RuntimeError("503 service unavailable api_key=SECRETKEY123456")

    with pytest.raises(AppError) as info:
        gw.call("ask", fn)
    assert info.value.category is C.PROVIDER and calls["n"] == 3
    assert log[0]["ok"] is False and log[0]["retries"] == 2 and "SECRETKEY123456" not in str(log[0])
    assert "SECRETKEY123456" not in info.value.technical


def test_permanent_errors_are_not_retried_and_do_not_fall_back_when_invalid_input():
    calls = {"n": 0}

    def fn(llm, cfg):
        calls["n"] += 1
        raise AppError(C.INVALID_INPUT, "bad")

    prefs = {"profiles": {"ask": {"provider": "Gemini", "fallback_provider": "Mistral"}}}
    with pytest.raises(AppError):
        make_gateway(FakeLLM(), prefs=prefs).call("ask", fn)
    assert calls["n"] == 1


def test_fallback_is_explicit_reported_and_logged(monkeypatch):
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    log, record = events()
    prefs = {"profiles": {"ask": {"provider": "Gemini", "model": "g", "fallback_provider": "Mistral", "fallback_model": "m"}}}
    seen = []

    def fn(llm, cfg):
        seen.append(llm)
        if llm == "primary":
            raise RuntimeError("429 rate limit")
        return "from fallback"

    run = PipelineRun("x", kind="ask")
    gw = make_gateway({"Gemini": "primary", "Mistral": "backup"}, prefs=prefs, record=record)
    assert gw.call("ask", fn, run=run, stage="answer") == "from fallback"
    assert gw.model_used("ask") == "Mistral:m" and gw.fallback_used["ask"] == "Gemini:g → Mistral:m"
    assert [e["fallback"] for e in log] == [False, True] and [e["ok"] for e in log] == [False, True]
    assert any("fallback" in ev.message for ev in run.view()[1])


def test_no_fallback_configured_means_no_silent_model_switch(monkeypatch):
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    gw = make_gateway({"Gemini": "primary", "Mistral": "backup"})
    with pytest.raises(AppError):
        gw.call("ask", lambda llm, cfg: (_ for _ in ()).throw(RuntimeError("429 rate limit")))
    assert gw.model_used("ask") == ""


def test_prepare_uses_fallback_when_primary_has_no_key():
    prefs = {"profiles": {"ask": {"provider": "Gemini", "fallback_provider": "Mistral"}}}
    gw = make_gateway(FakeLLM(), prefs=prefs, keys={"Mistral": "k" * 12})
    assert gw.prepare("ask").provider == "Mistral"


def test_circuit_breaker_pauses_a_failing_provider_then_recovers(monkeypatch):
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    now = {"t": 0.0}
    breaker = CircuitBreaker(threshold=2, window_s=100, cooldown_s=30, clock=lambda: now["t"])
    gw = make_gateway(FakeLLM(), breaker=breaker, max_attempts=1)
    fail = lambda llm, cfg: (_ for _ in ()).throw(RuntimeError("503 service unavailable"))
    for _ in range(2):
        with pytest.raises(AppError):
            gw.call("ask", fail)
    calls = {"n": 0}
    with pytest.raises(AppError) as info:
        gw.call("ask", lambda llm, cfg: calls.__setitem__("n", calls["n"] + 1))
    assert calls["n"] == 0 and "paused" in info.value.message and breaker.snapshot()
    now["t"] = 31.0
    assert gw.call("ask", lambda llm, cfg: "back") == "back" and not breaker.snapshot()


def test_auth_errors_do_not_trip_the_breaker():
    breaker = CircuitBreaker(threshold=1)
    gw = make_gateway(FakeLLM(), breaker=breaker, max_attempts=1)
    with pytest.raises(AppError):
        gw.call("ask", lambda llm, cfg: (_ for _ in ()).throw(RuntimeError("401 unauthorized")))
    assert breaker.allow("Gemini")


def test_budget_stop_and_known_invalid_key_preflight():
    gw = make_gateway(FakeLLM(), over_budget=lambda: True)
    with pytest.raises(AppError) as info:
        gw.call("ask", lambda llm, cfg: 1)
    assert info.value.category is C.BUDGET
    bad = make_gateway(FakeLLM(), preflight=lambda ref, key: AppError(C.AUTH, "rejected"))
    with pytest.raises(AppError) as info:
        bad.prepare("ask")
    assert info.value.category is C.AUTH


def test_output_validation_failure_is_a_failed_request():
    log, record = events()
    gw = make_gateway(FakeLLM(), record=record, max_attempts=1)

    def validate(result):
        raise AppError(C.MALFORMED, "empty", retryable=False)

    with pytest.raises(AppError):
        gw.call("ask", lambda llm, cfg: "", validate=validate)
    assert log[0]["ok"] is False and log[0]["stages"][-1]["ok"] is False
