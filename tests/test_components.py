from cinecritic.metadata import MovieMeta
from cinecritic.schemas import Dimension
from cinecritic.errors import AppError, ErrorCategory
from cinecritic.pipeline import PipelineRun
from cinecritic.services import Analysis, Reco
from cinecritic.ui.components import (
    compact, critique_grid_html, esc, events_html, featured_html, fmt_score, pipeline_html, reco_card_html,
    safe_image_url, timing_html, verdict_html,
)
from tests.helpers import dim, make_critique, make_recos


def _analysis(critique=None, meta=None, recos=()):
    return Analysis(query="Heat", critique=critique or make_critique(), meta=meta, recos=tuple(recos))


def test_esc_collapses_blank_lines_and_escapes():
    assert "\n" not in esc("a\n\nb <script>")
    assert "<script>" not in esc("<script>alert(1)</script>")


def test_compact_removes_inter_tag_whitespace():
    assert compact("<div>\n    <p>x</p>\n  </div>") == "<div><p>x</p></div>"


def test_image_urls_are_restricted_to_tmdb_https():
    assert safe_image_url("https://image.tmdb.org/t/p/w500/a.jpg")
    assert safe_image_url("http://image.tmdb.org/a.jpg") == ""
    assert safe_image_url("https://evil.example/a.jpg") == ""
    assert safe_image_url("javascript:alert(1)") == ""


def test_missing_scores_are_dashes_not_invented():
    assert fmt_score(-1) == "—" and fmt_score(None) == "—" and fmt_score(11) == "—"
    assert fmt_score(9.44) == "9.4"


def test_grid_has_nine_cards_and_escapes_model_text():
    c = make_critique(plot=Dimension(score=-1, summary="<b>x</b>", detail="", reference=""))
    out = critique_grid_html(_analysis(c))
    assert out.count('class="dim') == 9
    assert "<b>x</b>" not in out and "&lt;b&gt;" in out
    assert "bar off" in out  # unscored dimension shows no bar


def test_featured_uses_meta_when_available_and_fallback_otherwise():
    meta = MovieMeta(title="Heat", year="1995", director="Michael Mann",
                     backdrop_url="https://image.tmdb.org/t/p/w1280/b.jpg")
    with_meta = featured_html(_analysis(meta=meta))
    assert "image.tmdb.org" in with_meta and "Verified credits" in with_meta
    without = featured_html(_analysis())
    assert "image.tmdb.org" not in without and "unverified" in without


def test_verdict_is_not_forced_positive():
    c = make_critique(verdict_label="A Divisive but Ambitious Film", overall_score=5.1)
    assert "Divisive but Ambitious" in verdict_html(_analysis(c))


def test_reco_card_has_designed_fallback_without_poster():
    movie = make_recos()[1]
    assert 'class="ph"' in reco_card_html(Reco(movie, ""), 0)
    assert "<img" in reco_card_html(Reco(movie, "https://image.tmdb.org/t/p/w342/x.jpg"), 0)


def test_featured_shows_tmdb_rating_and_cast_separately_from_ai_score():
    meta = MovieMeta(title="Heat", rating=7.9, votes=9000, cast=(("Al Pacino", "Hanna"),))
    out = featured_html(_analysis(meta=meta))
    assert "TMDB 7.9" in out and "Al Pacino" in out and "CineCritic assessment" in out


def test_pipeline_html_reflects_real_stage_states_and_escapes():
    run = PipelineRun("Heat")
    run.start("search")
    run.complete("search", note="3 matches <b>x</b>")
    run.start("analysis")
    run.fail("analysis", AppError(ErrorCategory.AUTH, "rejected", technical="401"))
    run.skip("tmdb", "no key")
    out = compact(pipeline_html(run))
    assert out.count('class="stg ') == 7
    for cls in ("s-completed", "s-failed", "s-skipped", "s-pending"):
        assert cls in out
    assert "<b>x</b>" not in out and "&lt;b&gt;" in out
    assert "3 of 7 stages finished" in out and "Authentication" in out
    assert "role=\"progressbar\"" in out


def test_events_and_timing_html():
    run = PipelineRun("Heat")
    run.event("search", "warn", "attempt 1 failed; retrying")
    assert "ev-warn" in events_html(run) and "retrying" in events_html(run)
    run.start("analysis")
    run.complete("analysis", cached=True)
    run.finish()
    assert "reused from cache" in timing_html(_analysis().__class__(query="Heat", critique=make_critique(), run=run))


def test_pipeline_html_for_discover_run_has_its_own_five_stages():
    run = PipelineRun("heists", kind="discover")
    run.start("input")
    run.complete("input", note="6 characters")
    out = compact(pipeline_html(run))
    assert out.count('class="stg ') == 5 and "Request check" in out and "AI picks" in out
    assert "TMDB posters" in out and "run concurrently" not in out      # no parallel stages here
