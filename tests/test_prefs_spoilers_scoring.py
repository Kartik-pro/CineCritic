import pytest

from cinecritic import prefs, scoring, spoilers
from cinecritic.ai.providers import ModelRef
from cinecritic.config import PROVIDERS
from tests.helpers import make_critique, dim


# ---------------------------------------------------------------- preferences
def test_defaults_are_spoiler_free_and_valid():
    p = prefs.validate({})
    assert p["spoiler_level"] == "none" and p["score_scale"] == 10 and set(p["weights"]) == set(prefs.DEFAULTS["weights"])


def test_validation_clamps_and_drops_unknown_values():
    p = prefs.validate({"spoiler_level": "everything", "score_scale": 7, "request_timeout_s": 99999, "max_retries": 0,
                        "weights": {"plot": 99, "acting": -3, "bogus": 1}, "alert_threshold_pct": 1,
                        "creativity": 5, "daily_request_limit": -4, "language": "Klingon", "unknown": 1})
    assert p["spoiler_level"] == "none" and p["score_scale"] == 10 and p["language"] == "English"
    assert p["request_timeout_s"] == 180 and p["max_retries"] == 1
    assert p["weights"]["plot"] == 5.0 and p["weights"]["acting"] == 0.0 and "bogus" not in p["weights"]
    assert p["alert_threshold_pct"] == 10 and p["creativity"] == 1.0 and p["daily_request_limit"] == 0
    assert "unknown" not in p
    assert prefs.validate({"weights": {k: 0 for k in prefs.DEFAULTS["weights"]}})["weights"]["plot"] == 1.0


def test_profile_resolution_override_default_fallback_and_limits():
    p = prefs.validate({"default_provider": "Anthropic", "default_model": "claude-x",
                        "profiles": {"ask": {"provider": "OpenAI", "model": "gpt-z", "fallback_provider": "Gemini",
                                             "temperature": 0.4, "max_tokens": 10, "timeout_s": 1},
                                     "analysis": {"provider": "Nope"}}})
    ask = prefs.resolve_profile(p, "ask")
    assert ask.primary == ModelRef("OpenAI", "gpt-z") and ask.fallback == ModelRef("Gemini", PROVIDERS["Gemini"].default_model)
    assert ask.temperature == 0.4 and ask.max_tokens == 64 and ask.timeout_s == 10
    base = prefs.resolve_profile(p, "analysis")           # invalid override ignored -> global default
    assert base.primary == ModelRef("Anthropic", "claude-x") and base.fallback is None
    same = prefs.validate({"profiles": {"ask": {"provider": "Gemini", "model": "m", "fallback_provider": "Gemini",
                                                "fallback_model": "m"}}})
    assert prefs.resolve_profile(same, "ask").fallback is None       # fallback identical to primary is dropped


# ---------------------------------------------------------------- spoilers
def test_instructions_differ_by_level():
    assert "leave it as an empty string" in spoilers.instructions("none")
    assert "midpoint" in spoilers.instructions("light") and "ending" in spoilers.instructions("full")
    assert spoilers.effective_level("weird") == "none"


def test_clean_text_removes_only_the_offending_sentences():
    out, n = spoilers.clean_text("A tense, beautiful film. In the end the hero dies. The score is superb.", "none")
    assert n == 1 and "dies" not in out and "tense" in out and "superb" in out
    only, n2 = spoilers.clean_text("The twist is that he was dead all along.", "none")
    assert only == spoilers.PLACEHOLDER and n2 == 1
    assert spoilers.clean_text("Shot with restraint and warmth.", "none") == ("Shot with restraint and warmth.", 0)


def test_enforce_scrubs_every_section_and_respects_levels():
    c = make_critique(plot=dim(summary="The twist ending lands.", detail="Strong set-up."),
                      strengths=["Great ending reveals"], spoiler_notes="He dies at the end.")
    removed = spoilers.enforce(c, "none")
    assert removed >= 2 and c.spoiler_notes == "" and "twist" not in c.plot.summary.lower()
    full = make_critique(spoiler_notes="He dies at the end.")
    spoilers.enforce(full, "full")
    assert full.spoiler_notes == "He dies at the end."
    light = make_critique(spoiler_notes="Midpoint heist goes wrong. He dies in the finale.")
    spoilers.enforce(light, "light")
    assert "dies" not in light.spoiler_notes and "heist" in light.spoiler_notes


# ---------------------------------------------------------------- scoring
def test_weighted_overall_renormalises_and_never_counts_missing_as_zero():
    scores = {"plot": 8.0, "acting": 6.0, "direction": None}
    value, used, missing = scoring.weighted_overall(scores, {"plot": 1, "acting": 1, "direction": 1})
    assert value == 7.0 and used == ["plot", "acting"] and missing == ["direction"]
    assert scoring.weighted_overall(scores, {"plot": 3, "acting": 1})[0] == 7.5
    assert scoring.weighted_overall({"plot": None}, None)[0] is None


def test_scale_formatting_and_bands():
    assert scoring.fmt(8.5, 10) == "8.5" and scoring.fmt(8.5, 5) == "4.2" and scoring.fmt(8.5, 100) == "85"
    assert scoring.fmt(None) == "—" and scoring.band(9.5) == "Exceptional" and scoring.band(None) == "Not assessed"


def test_dimension_scores_validate_out_of_range_and_missing():
    c = make_critique(plot=dim(-1), acting=dim(11), direction=dim(7.0))
    s = scoring.dimension_scores(c)
    assert s["plot"] is None and s["acting"] is None and s["direction"] == 7.0


def test_comparison_rules_ties_insufficient_and_inconclusive():
    a = {"plot": 9, "screenplay": 9, "direction": 9, "acting": 9, "cinematography": 9, "music": 9, "pacing": 9, "themes": 9}
    b = {k: 6.0 for k in a}
    comp = scoring.compare_scores(a, b)
    assert comp.leader == "a" and all(r.outcome == "a" for r in comp.dims) and comp.decided == 8
    close = scoring.compare_scores(a, {k: 8.8 for k in a})
    assert close.leader == "too_close" and all(r.outcome == "tie" for r in close.dims)
    sparse = scoring.compare_scores({"plot": 9, "acting": 9}, {"plot": 2, "acting": 2})
    assert sparse.leader == "inconclusive" and any(r.outcome == "insufficient" for r in sparse.dims)
    # a missing category on one side cannot tilt the result
    one_missing = dict(b, plot=None)
    comp2 = scoring.compare_scores(a, one_missing)
    assert comp2.dims[0].outcome == "insufficient" and comp2.decided == 7
