import csv
import io
import json
import time

import pytest

from cinecritic import scoring
from cinecritic.features import awards, exports, monitoring
from cinecritic.features.battles import BattleResult
from cinecritic.features.compare_models import run_comparison
from cinecritic.ai.providers import ModelRef
from cinecritic.ai.usage import estimate_cost
from cinecritic.metadata import MovieMeta
from cinecritic.services import Analysis
from tests.helpers import FakeLLM, make_critique, dim

KEY = "AIzaSyFAKEKEY1234567890abcdefghij"


def a(title="Heat", level="none", notes="", **kw):
    return Analysis(query=title, critique=make_critique(title=title, spoiler_notes=notes, **kw),
                    meta=MovieMeta(title=title, tmdb_id=1, year="1995", runtime="2h 50m", genres=("Crime",),
                                   director="Michael Mann", cast=(("Al Pacino", "Hanna"),), rating=8.3, votes=9000),
                    model_used="Gemini:x", spoiler_level=level, created_at=time.time())


def text_of(pdf: bytes) -> str:
    assert pdf[:5] == b"%PDF-" and len(pdf) > 2000
    import re, zlib
    chunks = [zlib.decompress(m) for m in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S) if m[:2] in (b"x\x9c", b"x\xda", b"x\x01", b"x^")]
    return b"".join(chunks).decode("latin-1", "ignore")


def test_critique_pdf_builds_and_never_contains_secrets_or_hidden_spoilers():
    pdf = exports.critique_pdf(a(level="full", notes="The ending twist."), include_spoilers=False, user_rating=9.0)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 3000
    assert KEY.encode() not in pdf
    with_spoilers = exports.critique_pdf(a(level="full", notes="The ending twist."), include_spoilers=True)
    assert with_spoilers[:5] == b"%PDF-" and len(with_spoilers) != len(pdf)


def test_pdf_handles_unicode_missing_metadata_and_scales():
    crit = make_critique(title="Amélie — 千と千尋", plot=dim(-1), verdict_text="Café “noir” ☆")
    pdf = exports.critique_pdf(Analysis(query="x", critique=crit, meta=None), scale=100)
    assert pdf[:5] == b"%PDF-"
    assert exports.critique_pdf(a(), scale=5, weights={"plot": 3.0})[:5] == b"%PDF-"


def test_comparison_collection_and_awards_pdfs():
    comp = scoring.compare_scores(scoring.dimension_scores(make_critique()), scoring.dimension_scores(make_critique(direction=dim(5))))
    battle = BattleResult(a("Heat"), a("Collateral"), comp, "Two crime films.\nOverall: taste.", ("note",))
    assert exports.comparison_pdf(battle)[:5] == b"%PDF-"
    entries = [{"title": "Heat", "year": "1995", "status": "watched", "rating": 9.0, "favorite": True,
                "review": "Great", "notes": "Rewatch", "meta": {}}]
    assert exports.collection_pdf(entries)[:5] == b"%PDF-"
    films = {"h": ("Heat", scoring.dimension_scores(make_critique())), "c": ("Collateral", scoring.dimension_scores(make_critique(direction=dim(5))))}
    assert exports.awards_pdf(awards.run_awards(films, awards.default_categories()))[:5] == b"%PDF-"


def test_json_exports_respect_spoiler_opt_in_and_contain_no_credentials():
    x = a(level="full", notes="He dies.")
    assert json.loads(exports.analysis_json(x))["critique"]["spoiler_notes"] == ""
    assert json.loads(exports.analysis_json(x, include_spoilers=True))["critique"]["spoiler_notes"] == "He dies."
    none_level = a(level="none", notes="He dies.")
    assert json.loads(exports.analysis_json(none_level, include_spoilers=True))["critique"]["spoiler_notes"] == ""
    assert "api_key" not in exports.analysis_json(x).lower()


def test_csv_neutralises_formula_injection():
    entries = [{"title": "=HYPERLINK(\"x\")", "year": "2000", "status": "watched", "rating": None, "favorite": False,
                "review": "+cmd", "notes": "@x", "meta": {"genres": ["A", "B"], "tmdb_id": 5}}]
    rows = list(csv.reader(io.StringIO(exports.archive_csv(entries))))
    assert rows[1][0].startswith("'=") and rows[1][5].startswith("'+") and rows[1][6].startswith("'@")
    assert rows[1][7] == "A; B" and rows[1][9] == "5"
    assert json.loads(exports.archive_json(entries))["format"] == "cinecritic-collection"


def test_export_failure_is_a_clean_app_error(monkeypatch):
    monkeypatch.setattr(exports, "_para", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("layout bug")))
    with pytest.raises(exports.ExportError) as info:
        exports.critique_pdf(a())
    assert "could not be generated" in info.value.message


# ---------------------------------------------------------------- monitoring
def ev(ts, ok=True, provider="Gemini", model="m", in_t=100, out_t=50, lat=200, cat="", msg="", task="analysis", fb=False):
    return {"ts": ts, "provider": provider, "model": model, "task": task, "ok": ok, "error_category": cat,
            "error_message": msg, "latency_ms": lat, "in_tokens": in_t, "out_tokens": out_t, "retries": 0,
            "run_id": "", "fallback": fb, "stages": []}


def test_cost_estimates_use_only_configured_prices_and_known_tokens():
    assert estimate_cost(1_000_000, 500_000, {"in": 1.0, "out": 2.0}) == 2.0
    assert estimate_cost(None, 5, {"in": 1, "out": 1}) is None and estimate_cost(5, 5, None) is None


def test_summary_totals_tokens_latency_errors_and_unknowns():
    now = time.time()
    events = [ev(now), ev(now, lat=400), ev(now, ok=False, cat="rate_limit", msg="429 quota exceeded", in_t=None, out_t=None),
              ev(now, ok=False, cat="timeout", in_t=None, out_t=None), ev(now - 86400 * 40, provider="OpenAI", model="g")]
    s = monitoring.summarize(events, {"Gemini:m": {"in": 1.0, "out": 1.0}})
    assert s["total"] == 5 and s["ok"] == 3 and s["failed"] == 2
    assert s["input_tokens"] == 300 and s["calls_without_tokens"] == 2 and s["calls_with_tokens"] == 3
    assert s["rate_limit_events"] == 1 and s["quota_events"] == 1 and s["timeouts"] == 1
    assert s["latency_avg_ms"] == 267 and s["latency_p95_ms"] == 400
    assert abs(s["cost_usd"] - 0.0003) < 1e-9 and s["unpriced_calls"] == 3
    assert {m["provider"] for m in s["by_model"]} == {"Gemini", "OpenAI"} and len(s["monthly"]) >= 2
    assert monitoring.summarize([])["cost_usd"] is None and monitoring.summarize([])["latency_avg_ms"] is None
    only = monitoring.filter_events(events, provider="OpenAI")
    assert len(only) == 1 and len(monitoring.filter_events(events, since=now - 10)) == 4


def test_limits_alerts_and_hard_budget_stop():
    now = time.time()
    events = [ev(now, in_t=1_000_000, out_t=0) for _ in range(8)]
    prefs = {"daily_request_limit": 10, "monthly_budget_usd": 5.0, "alert_threshold_pct": 80, "hard_budget_stop": True,
             "pricing": {"Gemini:m": {"in": 1.0, "out": 0.0}}}
    limits = {l.name: l for l in monitoring.limit_statuses(events, prefs, now=now)}
    assert limits["Requests today"].level == "warn" and limits["Estimated spend this month"].level == "over"
    assert monitoring.over_budget(events, prefs, now) is True
    assert monitoring.over_budget(events, dict(prefs, hard_budget_stop=False), now) is False
    assert monitoring.limit_statuses(events, {"alert_threshold_pct": 80}, now=now) == []     # unknown limits are not invented
    assert monitoring.limit_statuses(events, prefs, now=now)[0].alert_key == "Requests today:warn"


def test_health_checks_report_real_facts():
    checks = monitoring.health_checks(
        workspace_counts={"archive": 2}, tmdb_configured=False, cache={"details_hits": 1, "details_misses": 3},
        breaker={"Gemini": 20.0}, recent_errors=2, config_problems=["x"],
        provider_state={"Gemini": {"configured": True, "package": True, "state": "valid", "detail": "ok"},
                        "OpenAI": {"configured": False, "package": True, "state": "", "detail": ""},
                        "Mistral": {"configured": True, "package": False, "state": "", "detail": ""}})
    by = {c.name: c for c in checks}
    assert by["Provider: Gemini"].level == "ok" and by["Provider: OpenAI"].level == "warn"
    assert by["Provider: Mistral"].level == "fail" and by["TMDB"].level == "warn"
    assert by["Circuit breaker"].level == "warn" and by["Recent errors"].level == "warn"
    assert "No database" in by["Workspace"].detail and "1/4" in by["Cache"].detail


def test_model_comparison_measures_each_model_and_isolates_failures():
    rec = []
    good, bad = FakeLLM(reply="Short answer."), FakeLLM(fail_chat=RuntimeError("401 unauthorized"))
    refs = [ModelRef("Gemini", "a"), ModelRef("Mistral", "b"), ModelRef("Gemini", "a")]
    rows = run_comparison(refs, "Explain a Dutch angle.", lambda p: "k" * 12,
                          builder=lambda ref, key, **kw: good if ref.provider == "Gemini" else bad,
                          record=lambda **kw: rec.append(kw))
    assert len(rows) == 2 and rows[0].ok and rows[0].output == "Short answer." and rows[0].latency_ms >= 0
    assert not rows[1].ok and rows[1].category == "auth"
    assert len(rec) == 2 and {r["task"] for r in rec} == {"comparison"}
    with pytest.raises(ValueError):
        run_comparison(refs, "  ", lambda p: "k")
