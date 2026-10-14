"""Scoring helpers: validation, display scales, transparent weighting and comparison rules.

Stored scores are always CineCritic AI assessments on 0-10 (never IMDb/audience scores). The display
scale is a presentation setting. Missing or malformed scores are excluded, never invented.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT_WEIGHTS, DIMENSIONS, SHORT_LABELS
from .schemas import Critique, valid_score

BANDS = ((9.0, "Exceptional"), (8.0, "Excellent"), (7.0, "Strong"), (6.0, "Solid"), (5.0, "Mixed"),
         (3.0, "Weak"), (0.0, "Poor"))
TIE_MARGIN = 0.3            # per-dimension scores closer than this are a tie
WINNER_MARGIN = 0.5         # weighted overall must differ by at least this to name a leader
MIN_DECIDED_DIMS = 4        # ...and at least this many dimensions must be comparable


def dimension_scores(c: Critique) -> dict[str, float | None]:
    return {key: valid_score(getattr(c, key).score) for key, _ in DIMENSIONS}


def weighted_overall(scores: dict[str, float | None], weights: dict[str, float] | None = None
                     ) -> tuple[float | None, list[str], list[str]]:
    """Weighted mean over the dimensions that have a valid score.

    Returns (value or None, used keys, missing keys). Weights are renormalised over available
    dimensions, so a missing category lowers confidence but never silently counts as zero.
    """
    weights = weights or DEFAULT_WEIGHTS
    used = [k for k, v in scores.items() if v is not None and weights.get(k, 0) > 0]
    missing = [k for k, v in scores.items() if v is None]
    total = sum(weights[k] for k in used)
    if not used or total <= 0:
        return None, used, missing
    return sum(scores[k] * weights[k] for k in used) / total, used, missing


def to_scale(score: float | None, scale: int = 10) -> float | None:
    return None if score is None else score / 10.0 * scale


def fmt(score: float | None, scale: int = 10) -> str:
    v = to_scale(score, scale)
    if v is None:
        return "—"
    return f"{v:.0f}" if scale == 100 else f"{v:.1f}"


def band(score: float | None) -> str:
    if score is None:
        return "Not assessed"
    return next(label for floor, label in BANDS if score >= floor)


def label(key: str) -> str:
    return SHORT_LABELS.get(key, key.title())


@dataclass(frozen=True)
class DimResult:
    key: str
    a: float | None
    b: float | None
    outcome: str        # 'a' | 'b' | 'tie' | 'insufficient'
    gap: float | None


@dataclass(frozen=True)
class Comparison:
    dims: tuple[DimResult, ...]
    overall_a: float | None
    overall_b: float | None
    leader: str         # 'a' | 'b' | 'too_close' | 'inconclusive'
    decided: int
    rule: str


def compare_scores(a: dict[str, float | None], b: dict[str, float | None],
                   weights: dict[str, float] | None = None) -> Comparison:
    """Transparent, deterministic comparison. 'leader' is a score-based reading, not a verdict on art."""
    dims = []
    for key, _ in DIMENSIONS:
        x, y = a.get(key), b.get(key)
        if x is None or y is None:
            dims.append(DimResult(key, x, y, "insufficient", None))
        elif abs(x - y) < TIE_MARGIN:
            dims.append(DimResult(key, x, y, "tie", abs(x - y)))
        else:
            dims.append(DimResult(key, x, y, "a" if x > y else "b", abs(x - y)))
    # Compare only on dimensions both films have, so a missing category cannot tilt the result.
    shared = {r.key for r in dims if r.outcome != "insufficient"}
    ca = {k: v for k, v in a.items() if k in shared}
    cb = {k: v for k, v in b.items() if k in shared}
    oa, _, _ = weighted_overall(ca, weights)
    ob, _, _ = weighted_overall(cb, weights)
    decided = len(shared)
    if oa is None or ob is None or decided < MIN_DECIDED_DIMS:
        leader = "inconclusive"
    elif abs(oa - ob) < WINNER_MARGIN:
        leader = "too_close"
    else:
        leader = "a" if oa > ob else "b"
    rule = (f"Scores are compared only on categories both films have ({decided} of {len(DIMENSIONS)}). Gaps under "
            f"{TIE_MARGIN} count as ties. A film leads overall only if the weighted averages differ by at least "
            f"{WINNER_MARGIN} and at least {MIN_DECIDED_DIMS} categories are comparable; otherwise the result is "
            "reported as too close or inconclusive. This describes CineCritic's AI scores, not artistic superiority.")
    return Comparison(tuple(dims), oa, ob, leader, decided, rule)
