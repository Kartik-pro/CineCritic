"""Turn analyses into plain JSON-safe dicts (for storage/backup/export) and back, with validation."""
from __future__ import annotations

import dataclasses
import time
from typing import Any

from ..metadata import Candidate, MovieMeta, normalize_title
from ..schemas import Critique, Movie
from ..services import Analysis, Reco

_META_FIELDS = {f.name for f in dataclasses.fields(MovieMeta)}


def film_key(title: str, meta: MovieMeta | None = None) -> str:
    """Stable archive key: the TMDB ID when known, otherwise the normalised title."""
    if meta is not None and meta.tmdb_id:
        return f"tmdb:{meta.tmdb_id}"
    return f"t:{normalize_title(title)}"


def analysis_key(a: Analysis) -> str:
    return film_key(a.critique.title or a.query, a.meta)


def meta_snapshot(a: Analysis) -> dict[str, Any]:
    """The compact facts other features (archive, quests, graph, awards) rely on."""
    c, m = a.critique, a.meta
    genres = list(m.genres) if m and m.genres else [g.strip() for g in c.genre.split(",") if g.strip()]
    return {
        "tmdb_id": m.tmdb_id if m else 0,
        "title": (m.title if m and m.title else c.title) or a.query,
        "year": (m.year if m and m.year else c.year) or "",
        "genres": genres,
        "director": (m.director if m and m.director else c.director) or "",
        "cast": [list(p) for p in (m.cast if m else ())],
        "language": m.language if m else "",
        "collection_id": m.collection_id if m else 0,
        "collection_name": m.collection_name if m else "",
        "poster_url": m.poster_url if m else "",
        "tmdb_rating": m.rating if m else None,
        "themes": list(c.themes_tags),
        "ai_overall": c.overall_score,
    }


def analysis_to_dict(a: Analysis) -> dict[str, Any]:
    return {
        "query": a.query,
        "critique": a.critique.model_dump(),
        "meta": dataclasses.asdict(a.meta) if a.meta else None,
        "recos": [{"movie": r.movie.model_dump(), "poster_url": r.poster_url} for r in a.recos],
        "alternatives": [dataclasses.asdict(c) for c in a.alternatives],
        "notices": list(a.notices),
        "model_used": a.model_used,
        "fallback": a.fallback,
        "spoiler_level": a.spoiler_level,
        "spoiler_removed": a.spoiler_removed,
        "created_at": a.created_at or time.time(),
    }


def _meta_from(d: dict | None) -> MovieMeta | None:
    if not isinstance(d, dict) or not d.get("title"):
        return None
    clean = {k: v for k, v in d.items() if k in _META_FIELDS}
    clean["genres"] = tuple(str(g) for g in clean.get("genres") or ())
    clean["cast"] = tuple((str(p[0]), str(p[1]) if len(p) > 1 else "") for p in clean.get("cast") or ()
                          if isinstance(p, (list, tuple)) and p)
    try:
        return MovieMeta(**clean)
    except TypeError:
        return None


def analysis_from_dict(d: dict[str, Any]) -> Analysis:
    """Rebuild an Analysis from stored data. Raises ValueError if the critique no longer validates."""
    if not isinstance(d, dict):
        raise ValueError("Stored analysis is malformed.")
    try:
        critique = Critique.model_validate(d.get("critique") or {})
    except Exception as exc:
        raise ValueError("Stored critique failed validation.") from exc
    recos = []
    for r in d.get("recos") or []:
        try:
            recos.append(Reco(Movie.model_validate(r["movie"]), str(r.get("poster_url") or "")))
        except Exception:
            continue
    alts = []
    for c in d.get("alternatives") or []:
        try:
            alts.append(Candidate(**{k: v for k, v in c.items() if k in {f.name for f in dataclasses.fields(Candidate)}}))
        except TypeError:
            continue
    return Analysis(
        query=str(d.get("query") or critique.title), critique=critique, meta=_meta_from(d.get("meta")),
        recos=tuple(recos), alternatives=tuple(alts), notices=tuple(str(n) for n in d.get("notices") or []),
        model_used=str(d.get("model_used") or ""), fallback=str(d.get("fallback") or ""),
        spoiler_level=str(d.get("spoiler_level") or "none"), spoiler_removed=int(d.get("spoiler_removed") or 0),
        created_at=float(d.get("created_at") or 0), from_storage=True,
    )
