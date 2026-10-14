import pytest

from cinecritic import pipeline
from cinecritic.errors import AppError, ErrorCategory as C, HTTPFailure
from cinecritic.pipeline import PipelineRun, Status, call_with_retries, diagnostics_text, stage_scope

KEY = "SECRETKEY99XYZ"


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_stage_transitions_and_duration():
    clock = Clock()
    run = PipelineRun("Heat", "m", clock=clock)
    assert run.stage("search").status is Status.PENDING
    run.start("search")
    clock.t = 1.5
    assert run.stage("search").status is Status.RUNNING and run.duration("search") == 1.5
    run.complete("search", note="ok")
    clock.t = 3.0
    assert run.stage("search").status is Status.COMPLETED and run.duration("search") == 1.5
    run.skip("tmdb", "no key")
    assert run.done_count() == (2, 7)
    assert run.overall == "running"
    run.finish()
    assert run.overall == "completed" and run.stage("render").status is Status.PENDING


def test_failed_analysis_is_failed_and_optional_failure_is_partial():
    run = PipelineRun("Heat")
    run.start("analysis")
    run.fail("analysis", AppError(C.AUTH, "bad key", technical="401"))
    run.finish()
    assert run.overall == "failed" and run.errors()[0].error.category is C.AUTH

    ok = PipelineRun("Heat")
    ok.complete("analysis")
    ok.fail("tmdb", AppError(C.TMDB, "down"))
    ok.finish()
    assert ok.overall == "partial"


def test_stage_scope_classifies_unexpected_errors():
    run = PipelineRun("Heat")
    with pytest.raises(AppError):
        with stage_scope(run, "process"):
            raise ZeroDivisionError("bug")
    assert run.stage("process").status is Status.FAILED
    assert run.stage("process").error.category is C.INTERNAL


def test_retries_transient_with_exponential_backoff(monkeypatch):
    delays = []
    monkeypatch.setattr(pipeline, "_sleep", delays.append)
    run = PipelineRun("Heat")
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise HTTPFailure(503)
        return "ok"

    assert call_with_retries(flaky, run=run, stage="tmdb", source="tmdb") == "ok"
    assert calls["n"] == 3 and len(delays) == 2
    assert delays[1] > delays[0]                         # exponential
    assert run.stage("tmdb").attempts == 3
    assert sum(e.level == "warn" for e in run.view()[1]) == 2


def test_permanent_errors_are_not_retried(monkeypatch):
    monkeypatch.setattr(pipeline, "_sleep", lambda d: (_ for _ in ()).throw(AssertionError("slept")))
    calls = {"n": 0}

    def bad_key():
        calls["n"] += 1
        raise RuntimeError("401 invalid api key")

    with pytest.raises(AppError) as info:
        call_with_retries(bad_key, source="ai")
    assert calls["n"] == 1 and info.value.category is C.AUTH


def test_gives_up_after_max_attempts_and_malformed_retries_once(monkeypatch):
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    n = {"a": 0, "b": 0}

    def always_down():
        n["a"] += 1
        raise HTTPFailure(503)

    def malformed():
        n["b"] += 1
        raise RuntimeError("1 validation error for Critique")

    with pytest.raises(AppError):
        call_with_retries(always_down, source="tmdb")
    with pytest.raises(AppError):
        call_with_retries(malformed, source="ai")
    assert n == {"a": 3, "b": 2}


def test_events_and_diagnostics_never_contain_secrets():
    run = PipelineRun("Heat", "Gemini:x")
    run.start("analysis")
    run.event("analysis", "info", f"debug api_key={KEY} Authorization: Bearer abcdefghijklmnop")
    run.fail("analysis", AppError(C.AUTH, "rejected", technical=f"401 token={KEY}"))
    text = diagnostics_text(run)
    assert KEY not in text and "abcdefghijklmnop" not in text
    assert run.run_id in text and "analysis" in text and "auth" in text
