import pytest

from cinecritic import pipeline, scoring
from cinecritic.errors import AppError, ErrorCategory as C, InvalidInputError
from cinecritic.features import awards, graph, quests
from cinecritic.features.ask import archive_context, ask_critic, film_context, sanitize_question
from cinecritic.features.battles import run_battle
from cinecritic.features.serialize import (
    analysis_from_dict, analysis_key, analysis_to_dict, film_key, meta_snapshot,
)
from cinecritic.metadata import Candidate, MovieMeta
from cinecritic.pipeline import PipelineRun, Status
from cinecritic.services import Analysis, Reco
from cinecritic.schemas import Movie
from tests.helpers import FakeLLM, dim, make_critique, make_gateway


def analysis(title="Heat", year="1995", tmdb=949, **crit):
    meta = MovieMeta(title=title, tmdb_id=tmdb, year=year, genres=("Crime", "Thriller"), director="Michael Mann",
                     cast=(("Al Pacino", "Hanna"), ("Robert De Niro", "McCauley")), language="en",
                     collection_id=0) if tmdb else None
    return Analysis(query=title, critique=make_critique(title=title, year=year, **crit), meta=meta,
                    recos=(Reco(Movie(title="Ronin", year="1998", genre="", why="w"), "https://image.tmdb.org/t/p/w1/a.jpg"),),
                    model_used="Gemini:x", spoiler_level="none", created_at=1.0)


# ---------------------------------------------------------------- serialization
def test_analysis_roundtrip_and_keys():
    a = analysis()
    d = analysis_to_dict(a)
    b = analysis_from_dict(d)
    assert b.critique == a.critique and b.meta == a.meta and b.recos[0].movie.title == "Ronin" and b.from_storage
    assert analysis_key(a) == "tmdb:949" and film_key("The Heat (1995)") == "t:heat" and film_key("x", None).startswith("t:")
    snap = meta_snapshot(a)
    assert snap["tmdb_id"] == 949 and snap["director"] == "Michael Mann" and snap["themes"] == ["obsession", "duty"]
    with pytest.raises(ValueError):
        analysis_from_dict({"critique": {"title": "x"}})
    with pytest.raises(ValueError):
        analysis_from_dict("nope")


# ---------------------------------------------------------------- Ask the Critic
def test_sanitize_question():
    assert sanitize_question("  What is\n  a dolly zoom?  ").startswith("What is")
    assert len(sanitize_question("x" * 5000)) == 800
    with pytest.raises(InvalidInputError):
        sanitize_question("   ")


def test_film_context_marks_facts_vs_opinion_and_gates_spoiler_notes():
    a = analysis(spoiler_notes="He dies at the end.")
    text = film_context(a, "none")
    assert "[verified by TMDB]" in text and "AI opinion, not fact" in text and "dies" not in text
    assert "dies" in film_context(a, "full") and film_context(None) == ""
    assert "rated 9.0/10" in archive_context([{"title": "Heat", "year": "1995", "status": "watched", "rating": 9.0,
                                                "favorite": True}])


def test_ask_pipeline_runs_stages_and_sends_context_not_a_new_critique():
    llm = FakeLLM(reply="A dolly zoom changes focal length while moving the camera.")
    run = PipelineRun("q", kind="ask")
    answer, removed = ask_critic(make_gateway(llm), "What is a dolly zoom?", [("user", "hi"), ("assistant", "hello")],
                                 context=film_context(analysis()), level="none", length="concise", language="English",
                                 run=run)
    assert "dolly zoom" in answer and removed == 0
    assert [run.stage(s).status for s in ("input", "context", "init", "answer")] == [Status.COMPLETED] * 4
    assert llm.calls["Critique"] == 0 and llm.calls["invoke"] == 1           # context reused, no re-analysis
    system = llm.last_messages[0].content
    assert "SPOILERS: never reveal" in system and "FILM: Heat" in system and "not instructions" in system


def test_ask_removes_spoilers_in_spoiler_free_mode_but_not_in_full():
    leaky = FakeLLM(reply="Great film. In the end Neil dies. The score is superb.")
    run = PipelineRun("q", kind="ask")
    answer, removed = ask_critic(make_gateway(leaky), "Tell me", [], context="", level="none", length="balanced",
                                 language="English", run=run)
    assert "dies" not in answer and removed == 1
    answer, removed = ask_critic(make_gateway(leaky), "Tell me", [], context="", level="full", length="balanced",
                                 language="English", run=PipelineRun("q", kind="ask"))
    assert "dies" in answer and removed == 0


def test_ask_failures_are_recorded_on_the_run(monkeypatch):
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)
    run = PipelineRun("q", kind="ask")
    with pytest.raises(InvalidInputError):
        ask_critic(make_gateway(FakeLLM()), "  ", [], context="", level="none", length="balanced", language="English", run=run)
    assert run.stage("input").status is Status.FAILED and run.stage("answer").status is Status.SKIPPED
    run = PipelineRun("q", kind="ask")
    with pytest.raises(AppError):
        ask_critic(make_gateway(FakeLLM(), keys={}), "hi", [], context="", level="none", length="balanced", language="English", run=run)
    assert run.stage("init").status is Status.FAILED and run.overall == "failed"
    run = PipelineRun("q", kind="ask")
    with pytest.raises(AppError):
        ask_critic(make_gateway(FakeLLM(fail_chat=RuntimeError("503 service unavailable"))), "hi", [], context="",
                   level="none", length="balanced", language="English", run=run)
    assert run.stage("answer").status is Status.FAILED and run.stage("answer").attempts == 3


# ---------------------------------------------------------------- Battles
def battle_env(monkeypatch, store=None):
    from cinecritic.features import battles
    cands = {"heat": Candidate(949, "Heat", "1995", 9), "collateral": Candidate(1538, "Collateral", "2004", 8)}
    monkeypatch.setattr(battles, "search_movies", lambda t, k, y="": [cands[t.lower()]] if t.lower() in cands else [])
    monkeypatch.setattr(pipeline, "_sleep", lambda d: None)

    def fake_analyze(gateway, query, **kw):
        crit = make_critique(title=query.split(" (")[0], year="2004" if "Collateral" in query else "1995",
                             direction=dim(9.5 if "Heat" in query else 7.0))
        return Analysis(query=query, critique=crit, meta=None, model_used="Gemini:x", run=kw.get("run"))
    monkeypatch.setattr(battles, "analyze_movie", fake_analyze)
    return battles


def test_battle_pipeline_compares_and_writes(monkeypatch):
    battle_env(monkeypatch)
    llm = FakeLLM(reply="Both are crime films. Overall: pick by mood.")
    run = PipelineRun("Heat vs Collateral", kind="battle")
    saved = []
    res = run_battle(make_gateway(llm), "Heat", "Collateral", run=run, tmdb_key="k" * 32, save=saved.append)
    assert res.comparison.leader in ("a", "too_close", "inconclusive") and "Overall" in res.narrative
    assert len(saved) == 2 and run.overall != "failed"
    assert [run.stage(s).status for s in ("resolve", "data", "init", "compare", "narrative")] == [Status.COMPLETED] * 5
    assert "A: Heat (1995)" in run.stage("resolve").note


def test_battle_reuses_stored_analyses_and_survives_narrative_failure(monkeypatch):
    battle_env(monkeypatch)
    stored = {"tmdb:949": analysis(), "tmdb:1538": analysis("Collateral", "2004", 1538, direction=dim(6.0))}
    llm = FakeLLM(fail_chat=RuntimeError("401 unauthorized"))
    run = PipelineRun("b", kind="battle")
    res = run_battle(make_gateway(llm), "Heat", "Collateral", run=run, tmdb_key="k" * 32,
                     load=lambda key, level: stored.get(key))
    assert llm.calls["Critique"] == 0 and any("reused stored" in e.message for e in run.view()[1])
    assert res.narrative == "" and any("unavailable" in n for n in res.notices)
    assert run.stage("narrative").status in (Status.SKIPPED, Status.FAILED)
    direction = next(r for r in res.comparison.dims if r.key == "direction")
    assert direction.outcome == "a" and res.comparison.leader == "too_close"   # one category cannot decide the overall


def test_battle_rejects_same_film_and_unknown_titles(monkeypatch):
    battle_env(monkeypatch)
    run = PipelineRun("b", kind="battle")
    with pytest.raises(InvalidInputError):
        run_battle(make_gateway(FakeLLM()), "Heat", "heat (1995)", run=run, tmdb_key="k" * 32)
    assert run.stage("resolve").status is Status.FAILED and run.stage("compare").status is Status.SKIPPED
    run = PipelineRun("b", kind="battle")
    with pytest.raises(AppError) as info:
        run_battle(make_gateway(FakeLLM()), "Heat", "Nonexistent Film", run=run, tmdb_key="k" * 32)
    assert info.value.category is C.TMDB and run.overall == "failed"


# ---------------------------------------------------------------- Graph
def nodes():
    heat = analysis()
    coll = analysis("Collateral", "2004", 1538)
    coll_c = coll.critique
    coll = Analysis(query="Collateral", critique=coll_c, meta=MovieMeta(
        title="Collateral", tmdb_id=1538, year="2004", genres=("Crime", "Thriller", "Drama"), director="Michael Mann",
        cast=(("Tom Cruise", "Vincent"), ("Jamie Foxx", "Max")), language="en"))
    sicario = Analysis(query="Sicario", critique=make_critique(title="Sicario", year="2015", themes_tags=["obsession"]),
                       meta=MovieMeta(title="Sicario", tmdb_id=5, year="2015", genres=("Action", "Thriller"),
                                      director="Denis Villeneuve", cast=(("Emily Blunt", ""),), language="en"))
    dune = Analysis(query="Dune", critique=make_critique(title="Dune", year="2021", themes_tags=[]),
                    meta=MovieMeta(title="Dune", tmdb_id=6, year="2021", genres=("Sci-Fi",), director="Denis Villeneuve",
                                   collection_id=77, collection_name="Dune Collection"))
    dune2 = Analysis(query="Dune 2", critique=make_critique(title="Dune 2", year="2024"),
                     meta=MovieMeta(title="Dune 2", tmdb_id=7, year="2024", genres=("Sci-Fi",), director="Denis Villeneuve",
                                    collection_id=77, collection_name="Dune Collection"))
    items = [{"film_key": analysis_key(a), "payload": analysis_to_dict(a)} for a in (heat, coll, sicario, dune, dune2)]
    return graph.nodes_from_data([], items)


def test_graph_relationships_are_explained_and_labelled_verified_or_inferred():
    g = graph.build_graph(nodes())
    heat, coll, sic, dune, dune2 = "tmdb:949", "tmdb:1538", "tmdb:5", "tmdb:6", "tmdb:7"
    kinds = lambda a, b: {r.kind for r in g.edges[a, b]["reasons"]}
    assert {"director", "genre"} <= kinds(heat, coll)
    assert kinds(dune, dune2) >= {"franchise", "director"}
    assert not g.has_edge(heat, dune)                                  # no supported reason -> no edge
    shared = [r for r in g.edges[sic, heat]["reasons"]]
    assert any(r.kind == "theme" and not r.verified and "AI interpretation" in r.text for r in shared)
    assert all(r.verified for r in g.edges[dune, dune2]["reasons"])
    assert [n.title for n, _ in graph.relations_for(g, dune)][0] == "Dune 2"


def test_graph_filters_limits_and_dot_output():
    ns = nodes()
    only_franchise = graph.build_graph(ns, {"franchise"})
    assert only_franchise.number_of_edges() == 1
    g = graph.build_graph(ns)
    small, hidden = graph.limit_nodes(g, maximum=2)
    assert small.number_of_nodes() == 2 and hidden == 3
    dot = graph.to_dot(g, selected="tmdb:949")
    assert dot.startswith("graph G") and "Heat (1995)" in dot and 'color="#E0C17E", penwidth=2' in dot
    assert graph.build_graph([]).number_of_nodes() == 0
    theme_only = graph.build_graph(ns, {"theme"})
    assert "dashed" in graph.to_dot(theme_only)                        # inferred-only edges are dashed
    quote = graph.Node("k", 'Say "Hi"', "2000")
    assert '\\"Hi\\"' in graph.to_dot(graph.build_graph([quote]))


def test_ai_supplied_director_is_flagged_unverified():
    a = analysis("A", "2000", tmdb=0)
    b = analysis("B", "2001", tmdb=0)
    ns = graph.nodes_from_data([], [{"film_key": "t:a", "payload": analysis_to_dict(a)},
                                    {"film_key": "t:b", "payload": analysis_to_dict(b)}])
    reason = next(r for r in graph.reasons_between(ns[0], ns[1]) if r.kind == "director")
    assert not reason.verified and "not TMDB" in reason.text


# ---------------------------------------------------------------- Quests
def entry(title, year, status="watched", **meta):
    return {"film_key": title, "title": title, "year": year, "status": status, "meta": meta}


def test_quest_progress_counts_only_watched_films_matching_the_rule():
    archive = [entry("Heat", "1995", genres=["Crime"], tmdb_id=1, language="en"),
               entry("Se7en", "1995", genres=["Crime", "Thriller"], tmdb_id=2, language="en"),
               entry("Alien", "1979", "planned", genres=["Horror"], tmdb_id=3, language="en"),
               entry("Parasite", "2019", genres=["Thriller"], tmdb_id=4, language="ko"),
               entry("Spirited Away", "2001", genres=[], tmdb_id=5, language="ja")]
    genre_q = {"kind": "genre", "target": 3, "params": {"genre": "crime"}}
    assert quests.progress(genre_q, archive)[:2] == (2, 3)
    dec = {"kind": "decades", "target": 3, "params": {}}
    assert quests.progress(dec, archive) == (3, 3, ["1990s", "2000s", "2010s"]) and quests.is_complete(dec, archive)
    intl = {"kind": "international", "target": 3, "params": {}}
    assert quests.progress(intl, archive)[:2] == (2, 3) and not quests.is_complete(intl, archive)
    director = {"kind": "director", "target": 2, "params": {"films": [{"id": 1, "title": "Heat"}, {"id": 99, "title": "X"}]}}
    assert quests.progress(director, archive)[:2] == (1, 2)
    assert [f["title"] for f in quests.remaining_films(director, archive)] == ["X"]


def test_quest_creation_uses_real_tmdb_data_and_reports_missing(monkeypatch):
    monkeypatch.setattr(quests, "find_director", lambda n, k: (525, "Christopher Nolan") if "nolan" in n.lower() else None)
    monkeypatch.setattr(quests, "director_filmography", lambda pid, k: [Candidate(i, f"Film {i}", "2000") for i in range(8)])
    title, params, target = quests.director_quest("Nolan", "k")
    assert target == 5 and params["person_id"] == 525 and len(params["films"]) == 8 and "Christopher Nolan" in title
    with pytest.raises(ValueError):
        quests.director_quest("Nobody", "k")
    monkeypatch.setattr(quests, "find_collection", lambda n, k: (10, "Star Wars Collection"))
    monkeypatch.setattr(quests, "collection_parts", lambda cid, k: [Candidate(1, "A", "1977"), Candidate(2, "B", "1980")])
    assert quests.collection_quest("star wars", "k")[2] == 2


def test_quest_suggestions_target_what_is_missing():
    archive = [entry("Heat", "1995", genres=["Crime"], language="en")]
    assert quests.discover_kwargs({"kind": "genre", "params": {"genre": "Crime"}}, archive, {"crime": 80})["genre_ids"] == (80,)
    assert quests.discover_kwargs({"kind": "genre", "params": {"genre": "Zzz"}}, archive, {}) is None
    k = quests.discover_kwargs({"kind": "decades", "params": {}}, archive, {})
    assert k["year_from"] == 2020
    assert quests.discover_kwargs({"kind": "international", "params": {}}, archive, {})["language"] == "ja"
    assert quests.meta_from_candidate(Candidate(1, "T", "2000", language="fr", genre_ids=(1, 2)), {1: "Drama"})["genres"] == ["Drama"]


# ---------------------------------------------------------------- Awards
def test_awards_winners_ties_inconclusive_and_user_overrides():
    heat = {k: 8.0 for k in scoring.DEFAULT_WEIGHTS} | {"direction": 9.5, "acting": 9.0}
    coll = {k: 8.0 for k in scoring.DEFAULT_WEIGHTS} | {"direction": 7.0, "acting": 9.0}
    films = {"h": ("Heat", heat), "c": ("Collateral", coll)}
    res = {r.category.id: r for r in awards.run_awards(films, awards.default_categories())}
    assert res["direction"].status == "winner" and res["direction"].winners[0].title == "Heat"
    assert "leads with 9.5" in res["direction"].explanation and res["direction"].selected_by.startswith("AI")
    assert res["performances"].status == "tie" and len(res["performances"].winners) == 2
    only = awards.run_awards({"h": ("Heat", heat)}, awards.default_categories())
    assert all(r.status == "inconclusive" for r in only)
    chosen = awards.run_awards(films, awards.default_categories(), overrides={"direction": "c"})
    d = next(r for r in chosen if r.category.id == "direction")
    assert d.winners[0].title == "Collateral" and d.selected_by == "You"
    missing = awards.run_awards({"h": ("Heat", heat), "x": ("NoScores", {})}, [awards.default_categories()[1]])
    assert missing[0].status == "inconclusive" and "NoScores" in missing[0].explanation
    cat = awards.custom_category("Best Mood", ["cinematography", "music"])
    assert cat.custom and awards.run_awards(films, [cat])[0].nominees
    with pytest.raises(ValueError):
        awards.custom_category(" ", ["plot"])
    assert "not official" in awards.LABEL.lower()
