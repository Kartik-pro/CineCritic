import pytest

from cinecritic import metadata, pipeline
from cinecritic.cache import TTLCache
from cinecritic.errors import AppError, ErrorCategory as C, HTTPFailure, InvalidInputError
from cinecritic.metadata import Candidate, MovieMeta, Selection
from cinecritic.pipeline import PipelineRun, Status
from cinecritic.services import (
    Analysis, analyze_movie, exclude_titles, facts_text, sanitize_query, to_bullets, to_text,
)
from tests import helpers
from tests.helpers import FakeLLM, make_critique, make_gateway, make_recos

KEY = "0123456789abcdef0123456789abcdef"


def caches():
    return {"critique_cache": TTLCache(60, 16), "recos_cache": TTLCache(60, 16)}




def setup_function(_):
    metadata.clear_cache()


def patch_tmdb(monkeypatch, *, search_fail=None, details_fail=None):
    from cinecritic import services

    def search(title, key, year=""):
        if search_fail:
            raise search_fail
        return [Candidate(949, "Heat", "1995", 60, poster_url="https://image.tmdb.org/t/p/w342/h.jpg")]

    def details(movie_id, key):
        if details_fail:
            raise details_fail
        return MovieMeta(title="Heat", tmdb_id=949, year="1995", director="Michael Mann", cast=(("Al Pacino", "Hanna"),)), False

    monkeypatch.setattr(services, "search_movies", search)
    monkeypatch.setattr(services, "fetch_details", details)
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)


def test_text_helpers():
    assert to_text([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "a\nb"
    text = "\n".join(f"- {' '.join(['word'] * 12)}" for _ in range(8))
    assert sum(len(b.split()) for b in to_bullets(text, 50)) <= 51
    assert sanitize_query("  Heat \n (1995) ") == "Heat (1995)"
    assert len(sanitize_query("x" * 500)) == 120
    with pytest.raises(InvalidInputError):
        sanitize_query("   ")
    assert all(m.title != "Heat" for m in exclude_titles(make_recos(), "heat"))


def test_facts_text_only_contains_verified_fields():
    assert facts_text(None) == ""
    out = facts_text(MovieMeta(title="Heat", director="Michael Mann", cast=(("Al Pacino", "Hanna"),)))
    assert "Verified facts (TMDB)" in out and "Michael Mann" in out and "Al Pacino as Hanna" in out


def test_no_tmdb_key_skips_data_stages_and_still_analyses():
    llm = FakeLLM()
    a = analyze_movie(make_gateway(llm), "Heat", **caches())
    run = a.run
    assert [run.stage(s).status for s in ("search", "tmdb", "process")] == [Status.SKIPPED] * 3
    assert all(run.stage(s).status is Status.COMPLETED for s in ("init", "analysis", "recommend"))
    assert run.overall == "completed" and a.model_used.startswith("Gemini:")
    assert "Heat" not in [r.movie.title for r in a.recos] and len(a.recos) == 4


def test_full_pipeline_with_tmdb_reuses_ids_and_marks_stages(monkeypatch):
    patch_tmdb(monkeypatch)
    a = analyze_movie(make_gateway(FakeLLM()), "Heat (1995)", tmdb_key=KEY, **caches())
    assert a.meta.tmdb_id == 949
    states = {s: a.run.stage(s).status for s in ("search", "tmdb", "process", "init", "analysis", "recommend")}
    assert set(states.values()) == {Status.COMPLETED}
    assert "TMDB #949" in a.run.stage("search").note


def test_second_run_reuses_cached_results_without_new_model_calls(monkeypatch):
    patch_tmdb(monkeypatch)
    llm, c = FakeLLM(), caches()
    gw = make_gateway(llm)
    analyze_movie(gw, "Heat (1995)", tmdb_key=KEY, **c)
    calls = dict(llm.calls)
    second = analyze_movie(gw, "heat (1995)", tmdb_key=KEY, **c)
    assert second.cached and second.run.stage("analysis").cached and dict(llm.calls) == calls


def test_cache_is_separate_per_spoiler_level_and_model(monkeypatch):
    llm, c = FakeLLM(), caches()
    analyze_movie(make_gateway(llm), "Heat", **c)
    analyze_movie(make_gateway(llm), "Heat", spoiler_level="full", **c)
    analyze_movie(make_gateway(llm, prefs={"default_provider": "Mistral"}), "Heat", **c)
    assert llm.calls["Critique"] == 3


def test_tmdb_failure_degrades_to_partial_but_analysis_succeeds(monkeypatch):
    patch_tmdb(monkeypatch, search_fail=HTTPFailure(503))
    a = analyze_movie(make_gateway(FakeLLM()), "Heat", tmdb_key=KEY, **caches())
    run = a.run
    assert a.critique.title == "Heat" and a.meta is None
    assert run.stage("search").status is Status.FAILED and run.stage("search").attempts == 3
    assert run.stage("tmdb").status is Status.SKIPPED and run.overall == "partial"


def test_tmdb_auth_failure_is_not_retried(monkeypatch):
    patch_tmdb(monkeypatch, search_fail=HTTPFailure(401))
    a = analyze_movie(make_gateway(FakeLLM()), "Heat", tmdb_key=KEY, **caches())
    assert a.run.stage("search").attempts == 1
    assert a.run.stage("search").error.category is C.AUTH


def test_missing_ai_key_fails_init_and_skips_generation():
    run = PipelineRun("Heat")
    with pytest.raises(AppError) as info:
        analyze_movie(make_gateway(FakeLLM(), keys={}), "Heat", run=run, **caches())
    assert info.value.category is C.AUTH
    assert run.stage("init").status is Status.FAILED
    assert run.stage("analysis").status is Status.SKIPPED and run.stage("recommend").status is Status.SKIPPED
    assert run.overall == "failed"


def test_critique_failure_raises_and_is_not_cached(monkeypatch):
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    c = caches()
    with pytest.raises(AppError) as info:
        analyze_movie(make_gateway(FakeLLM(fail_critique=RuntimeError("401 unauthorized"))), "Heat", **c)
    assert info.value.category is C.AUTH and len(c["critique_cache"]) == 0


def test_partial_recommendations_do_not_cache_and_keep_critique(monkeypatch):
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    c = caches()
    a = analyze_movie(make_gateway(FakeLLM(fail_recos=True)), "Heat", **c)
    assert a.critique.title == "Heat" and a.recos == () and a.notices
    assert a.run.stage("recommend").status is Status.FAILED and a.run.overall == "partial"
    assert len(c["recos_cache"]) == 0 and len(c["critique_cache"]) == 1


def test_unrecognised_film_is_not_cached():
    c = caches()
    a = analyze_movie(make_gateway(FakeLLM(make_critique(recognized=False))), "Asdfgh", **c)
    assert not a.critique.recognized and len(c["critique_cache"]) == 0


def test_invalid_input_fails_search_stage():
    run = PipelineRun("   ")
    with pytest.raises(InvalidInputError):
        analyze_movie(make_gateway(FakeLLM()), "   ", run=run, **caches())
    assert run.stage("search").error.category is C.INVALID_INPUT and run.overall == "failed"


def test_spoiler_filter_cleans_a_leaky_critique_and_reports_it():
    leaky = make_critique(verdict_text="A superb thriller. In the end the hero dies.",
                          spoiler_notes="The ending reveals everything.")
    a = analyze_movie(make_gateway(FakeLLM(leaky)), "Heat", n_recs=0, **caches())
    assert "dies" not in a.critique.verdict_text and a.critique.spoiler_notes == ""
    assert a.spoiler_removed >= 1 and any("spoiler" in n.lower() for n in a.notices)
    assert a.run.stage("recommend").status is Status.SKIPPED and a.recos == ()


def test_full_level_keeps_spoiler_notes_but_never_in_main_sections():
    c = make_critique(spoiler_notes="The ending: both men die.")
    a = analyze_movie(make_gateway(FakeLLM(c)), "Heat", spoiler_level="full", n_recs=0, **caches())
    assert a.critique.spoiler_notes.startswith("The ending") and a.spoiler_level == "full"


def test_fallback_model_is_used_only_when_configured_and_is_reported(monkeypatch):
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    bad, good = FakeLLM(fail_critique=RuntimeError("503 service unavailable")), FakeLLM()
    prefs = {"profiles": {"analysis": {"provider": "Gemini", "model": "g1", "fallback_provider": "Mistral",
                                        "fallback_model": "m1"}}}
    a = analyze_movie(make_gateway({"Gemini": bad, "Mistral": good}, prefs=prefs), "Heat", n_recs=0, **caches())
    assert a.model_used == "Mistral:m1" and a.fallback == "Gemini:g1 → Mistral:m1"
    assert any("fallback" in n.lower() for n in a.notices)
    # no fallback configured -> the failure surfaces instead of silently switching models
    with pytest.raises(AppError):
        analyze_movie(make_gateway({"Gemini": bad, "Mistral": good}), "Heat", n_recs=0, **caches())


def test_suggest_titles_only_returns_titles_tmdb_confirms(monkeypatch):
    from cinecritic import services
    monkeypatch.setattr(services, "search_movies",
                        lambda t, k, y="": [Candidate(len(t), t, y or "2000", 5)] if t in ("Collateral", "Ronin") else [])
    found = services.suggest_titles(make_gateway(FakeLLM()), "neon-lit night crime", KEY)
    assert {c.title for c in found} == {"Collateral", "Ronin"}


def test_extract_filters_validates_model_output(monkeypatch):
    from cinecritic import services
    from cinecritic.schemas import SearchFilters

    class FilterLLM(FakeLLM):
        def with_structured_output(self, schema):
            from langchain_core.runnables import RunnableLambda
            return RunnableLambda(lambda _: SearchFilters(genres=["Horror", "Nonsense"], year_from=1980, year_to=3000,
                                                          language="JAPANESE"))

    out = services.extract_filters(make_gateway(FilterLLM()), "80s horror", ["Horror", "Drama"])
    assert out.genres == ["Horror"] and out.year_from == 1980 and out.year_to == 0 and out.language == ""


# ------------------------------------------------------------------ Discover pipeline
def test_discover_pipeline_stages_and_results(monkeypatch):
    from cinecritic.services import discover_movies
    patch_tmdb(monkeypatch)
    run = PipelineRun("cozy heist movies", "m", kind="discover")
    recos = discover_movies(make_gateway(FakeLLM()), "cozy heist movies", run=run, tmdb_key=KEY, n=4)
    assert len(recos) == 6 and recos[0].poster_url.startswith("https://image.tmdb.org/")
    assert [s.id for s in run.view()[0]] == ["input", "init", "recommend", "posters", "render"]
    assert all(run.stage(s).status is Status.COMPLETED for s in ("input", "init", "recommend", "posters"))
    assert run.overall == "completed" and run.stage("render").status is Status.PENDING


def test_discover_without_tmdb_skips_posters():
    from cinecritic.services import discover_movies
    run = PipelineRun("x", kind="discover")
    discover_movies(make_gateway(FakeLLM()), "mind-bending thrillers", run=run)
    assert run.stage("posters").status is Status.SKIPPED and run.overall == "completed"


def test_discover_poster_outage_is_partial_but_picks_survive(monkeypatch):
    from cinecritic.services import discover_movies
    patch_tmdb(monkeypatch, search_fail=HTTPFailure(503))
    run = PipelineRun("x", kind="discover")
    recos = discover_movies(make_gateway(FakeLLM()), "heists", run=run, tmdb_key=KEY)
    assert recos and not any(r.poster_url for r in recos)
    assert run.stage("posters").status is Status.FAILED and run.overall == "partial"


def test_discover_invalid_input_and_missing_key_fail_the_run(monkeypatch):
    from cinecritic.services import discover_movies
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    bad = PipelineRun("", kind="discover")
    with pytest.raises(InvalidInputError):
        discover_movies(make_gateway(FakeLLM()), "   ", run=bad)
    assert bad.stage("input").status is Status.FAILED and bad.stage("init").status is Status.SKIPPED
    run = PipelineRun("x", kind="discover")
    with pytest.raises(AppError):
        discover_movies(make_gateway(FakeLLM(), keys={}), "heists", run=run)
    assert run.stage("init").status is Status.FAILED and run.stage("recommend").status is Status.SKIPPED
    assert run.overall == "failed"


def test_discover_ai_failure_after_setup_raises_and_marks_recommend_failed(monkeypatch):
    from cinecritic.services import discover_movies
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    run = PipelineRun("x", kind="discover")
    with pytest.raises(AppError):
        discover_movies(make_gateway(FakeLLM(fail_recos=True)), "heists", run=run)
    assert run.stage("recommend").status is Status.FAILED and run.stage("posters").status is Status.SKIPPED
    assert run.overall == "failed"
