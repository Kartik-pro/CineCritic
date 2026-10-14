"""CineCritic Award Nights: transparent category winners computed from existing analyses.

Winners are AI-generated *from CineCritic's own craft scores* (never real-world awards) and are
computed deterministically, so no extra model calls are needed. Users can override any winner,
and overrides are labelled "user-selected".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import scoring
from ..config import DIMENSIONS, SHORT_LABELS

TIE_MARGIN = 0.15
MIN_NOMINEES = 2

# id -> (title, {dimension: weight}, criteria text)
CATEGORIES: dict[str, tuple[str, dict[str, float], str]] = {
    "screenplay": ("Best Screenplay", {"screenplay": 1.0, "plot": 0.5},
                   "Screenplay score, with plot & premise at half weight."),
    "direction": ("Best Direction", {"direction": 1.0}, "Direction & vision score."),
    "vision": ("Best Cinematic Vision", {"cinematography": 1.0, "direction": 0.5},
               "Cinematography score, with direction at half weight."),
    "performances": ("Best Performances", {"acting": 1.0}, "Acting & performances score."),
    "editing": ("Best Editing", {"pacing": 1.0}, "Editing & pacing score."),
    "sound": ("Best Sound & Music", {"music": 1.0}, "Music & sound design score."),
    "emotion": ("Best Emotional Impact", {"themes": 1.0}, "Emotional impact & themes score."),
    "overall": ("Best Overall", {}, "Weighted overall of all eight categories using your preference weights."),
}


@dataclass(frozen=True)
class Category:
    id: str
    title: str
    weights: dict[str, float]
    criteria: str
    custom: bool = False


def default_categories() -> list[Category]:
    return [Category(i, t, dict(w), c) for i, (t, w, c) in CATEGORIES.items()]


def custom_category(name: str, dims: list[str]) -> Category:
    dims = [d for d in dims if d in SHORT_LABELS]
    if not name.strip() or not dims:
        raise ValueError("A custom category needs a name and at least one craft dimension.")
    weights = {d: 1.0 for d in dims}
    return Category("custom:" + name.strip().lower().replace(" ", "-")[:40], name.strip()[:60], weights,
                    "Average of: " + ", ".join(SHORT_LABELS[d] for d in dims) + ".", custom=True)


@dataclass(frozen=True)
class Nominee:
    key: str
    title: str
    score: float | None


@dataclass(frozen=True)
class AwardResult:
    category: Category
    nominees: tuple[Nominee, ...]
    status: str                     # 'winner' | 'tie' | 'inconclusive'
    winners: tuple[Nominee, ...]
    selected_by: str                # 'AI (score-based)' | 'You'
    explanation: str


def category_score(scores: dict[str, float | None], cat: Category, weights: dict[str, float] | None) -> float | None:
    if not cat.weights:      # overall
        return scoring.weighted_overall(scores, weights)[0]
    return scoring.weighted_overall(scores, cat.weights)[0] if any(
        scores.get(k) is not None for k in cat.weights) else None


def run_awards(films: dict[str, tuple[str, dict[str, float | None]]], categories: list[Category],
               weights: dict[str, float] | None = None, overrides: dict[str, str] | None = None) -> list[AwardResult]:
    """films: key -> (title, dimension scores). overrides: category id -> film key chosen by the user."""
    overrides = overrides or {}
    results = []
    for cat in categories:
        nominees = tuple(sorted((Nominee(k, t, category_score(s, cat, weights)) for k, (t, s) in films.items()),
                                key=lambda n: (n.score is None, -(n.score or 0))))
        scored = [n for n in nominees if n.score is not None]
        chosen = overrides.get(cat.id)
        if chosen and chosen in films:
            winner = next(n for n in nominees if n.key == chosen)
            results.append(AwardResult(cat, nominees, "winner", (winner,), "You",
                                       f"You selected {winner.title}. CineCritic's scores for this category: " +
                                       _score_line(nominees) + "."))
            continue
        if len(scored) < MIN_NOMINEES:
            missing = [n.title for n in nominees if n.score is None]
            why = ("Not enough films have scores for this category" +
                   (f" (missing: {', '.join(missing)})" if missing else "") + ".")
            results.append(AwardResult(cat, nominees, "inconclusive", (), "AI (score-based)", why))
            continue
        top = scored[0].score
        tied = tuple(n for n in scored if top - n.score < TIE_MARGIN)
        if len(tied) > 1:
            results.append(AwardResult(cat, nominees, "tie", tied, "AI (score-based)",
                                       "Too close to call: " + _score_line(tied) + f" (within {TIE_MARGIN})."))
        else:
            runner = scored[1]
            results.append(AwardResult(cat, nominees, "winner", (scored[0],), "AI (score-based)",
                                       f"{scored[0].title} leads with {top:.1f}/10; runner-up {runner.title} "
                                       f"scores {runner.score:.1f}. Criteria: {cat.criteria}"))
    return results


def _score_line(nominees) -> str:
    return ", ".join(f"{n.title} {n.score:.1f}" if n.score is not None else f"{n.title} n/a" for n in nominees)


LABEL = ("AI-generated from CineCritic's own scores. These are not official awards, and scores are subjective "
         "AI assessments.")
