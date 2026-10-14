"""Shared fixtures: a fake LLM and gateway so no test ever touches a real provider."""
from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

from langchain_core.runnables import RunnableLambda

from cinecritic import prefs as prefs_mod
from cinecritic.ai.gateway import Gateway
from cinecritic.config import PROVIDERS
from cinecritic.schemas import Critique, Dimension, Movie, Recommendations


def dim(score: float = 8.0, summary: str = "Strong.", detail: str = "Because craft.", ref: str = "CRAFT") -> Dimension:
    return Dimension(score=score, summary=summary, detail=detail, reference=ref)


def make_critique(**overrides) -> Critique:
    base = dict(
        recognized=True, title="Heat", year="1995", genre="Crime, Thriller", runtime="2h 50m",
        director="Michael Mann", cinematographer="", composer="",
        plot=dim(8.5), screenplay=dim(8.0), direction=dim(9.0), acting=dim(9.0),
        cinematography=dim(8.8), music=dim(7.5), pacing=dim(7.0), themes=dim(8.2),
        strengths=["Operatic set pieces", "Two towering leads"], flaws=["Overlong middle act"],
        overall_score=8.7, verdict_label="A Modern Crime Classic",
        pull_quote="A cool, melancholy duel between two professionals.",
        verdict_text="Meticulous and emotionally resonant despite its length.",
        recommendation="Watch on the biggest screen you can",
        quick_take=["- Taut crime epic.", "- De Niro and Pacino excel.", "- Superb direction. 8.7/10"],
        themes_tags=["obsession", "duty"], spoiler_notes="",
    )
    base.update(overrides)
    return Critique(**base)


def make_recos() -> list[Movie]:
    return [
        Movie(title="Heat", year="1995", genre="Crime", why="Itself"),
        Movie(title="Collateral", year="2004", genre="Thriller", why="Mann's neon-lit night crime."),
        Movie(title="The Town", year="2010", genre="Crime", why="Heist crew with divided loyalties."),
        Movie(title="Ronin", year="1998", genre="Action", why="Professionals, double-crosses, car chases."),
        Movie(title="Miami Vice", year="2006", genre="Crime", why="Mann's digital-noir style."),
        Movie(title="Sicario", year="2015", genre="Thriller", why="Moral fog and tense set pieces."),
    ]


class FakeLLM:
    """Mimics `llm.with_structured_output(schema)` and `llm.invoke(...)`; counts calls."""

    def __init__(self, critique: Critique | None = None, fail_recos: bool = False, reply: str = "A fine answer.",
                 fail_chat: Exception | None = None, fail_critique: Exception | None = None):
        self.critique = critique or make_critique()
        self.fail_recos, self.reply, self.fail_chat, self.fail_critique = fail_recos, reply, fail_chat, fail_critique
        self.calls: Counter = Counter()
        self.last_messages = None

    def with_structured_output(self, schema):
        def run(_):
            self.calls[schema.__name__] += 1
            if schema is Critique:
                if self.fail_critique:
                    raise self.fail_critique
                return self.critique.model_copy(deep=True)
            if self.fail_recos:
                raise RuntimeError("recommendation backend down")
            return Recommendations(recommendations=make_recos())

        return RunnableLambda(run)

    def invoke(self, messages, config=None):
        self.calls["invoke"] += 1
        self.last_messages = messages
        if self.fail_chat:
            raise self.fail_chat
        return SimpleNamespace(content=self.reply)


def make_gateway(llm=None, prefs=None, keys=None, record=None, **kwargs) -> Gateway:
    """Gateway whose builder returns `llm` (or llm[ref.provider] when a dict is given)."""
    prefs = prefs_mod.validate(prefs or {})
    keys = {p: "k" * 12 for p in PROVIDERS} if keys is None else keys
    llm = llm or FakeLLM()

    def builder(ref, key, **_):
        return llm[ref.provider] if isinstance(llm, dict) else llm

    return Gateway(profile_for=lambda t: prefs_mod.resolve_profile(prefs, t), key_for=lambda p: keys.get(p, ""),
                   record=record, builder=builder, **kwargs)
