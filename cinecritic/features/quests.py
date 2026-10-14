"""Discovery Quests: optional challenges whose progress is derived from the user's archive.

A film counts toward a quest only when the user marked it *watched* and its stored metadata (from
TMDB when available) satisfies the quest rule. Nothing is awarded for films the app merely suggested.
"""
from __future__ import annotations

from typing import Any

from ..metadata import Candidate, collection_parts, director_filmography, find_collection, find_director

KINDS = {
    "genre": "Explore a genre",
    "director": "A director's filmography",
    "decades": "Across the decades",
    "international": "World cinema",
    "collection": "Complete a franchise",
}
INTERNATIONAL_SUGGESTIONS = ("ja", "ko", "fr", "es", "hi", "it", "de", "pt", "zh", "sv")
LANGUAGE_NAMES = {"ja": "Japanese", "ko": "Korean", "fr": "French", "es": "Spanish", "hi": "Hindi", "it": "Italian",
                  "de": "German", "pt": "Portuguese", "zh": "Chinese", "sv": "Swedish", "en": "English"}


def meta_from_candidate(c: Candidate, genres: dict[int, str] | None = None) -> dict[str, Any]:
    """Archive snapshot for a film saved straight from a TMDB listing."""
    names = [genres[g] for g in c.genre_ids if genres and g in genres]
    return {"tmdb_id": c.id, "title": c.title, "year": c.year, "genres": names, "director": "", "cast": [],
            "language": c.language, "collection_id": 0, "collection_name": "", "poster_url": c.poster_url,
            "tmdb_rating": c.rating, "themes": [], "ai_overall": None}


# --------------------------------------------------------------------------- creation
def genre_quest(genre: str, target: int = 5) -> tuple[str, dict, int]:
    return f"Watch {target} {genre} films", {"genre": genre}, target


def decades_quest(target: int = 5) -> tuple[str, dict, int]:
    return f"Watch films from {target} different decades", {}, target


def international_quest(target: int = 3) -> tuple[str, dict, int]:
    return f"Watch films in {target} languages other than English", {}, target


def director_quest(name: str, key: str, target: int | None = None) -> tuple[str, dict, int]:
    """Real filmography from TMDB (raises AppError on lookup failure; ValueError if no match)."""
    person = find_director(name, key)
    if person is None:
        raise ValueError(f"TMDB has no director named “{name}”.")
    films = director_filmography(person[0], key)
    if not films:
        raise ValueError(f"TMDB lists no released films directed by {person[1]}.")
    films = films[:12]
    goal = min(target or 5, len(films))
    params = {"person_id": person[0], "person": person[1],
              "films": [{"id": f.id, "title": f.title, "year": f.year} for f in films]}
    return f"Watch {goal} films directed by {person[1]}", params, goal


def collection_quest(name: str, key: str) -> tuple[str, dict, int]:
    found = find_collection(name, key)
    if found is None:
        raise ValueError(f"TMDB has no collection named “{name}”.")
    parts = collection_parts(found[0], key)
    if not parts:
        raise ValueError(f"The “{found[1]}” collection has no listed films.")
    params = {"collection_id": found[0], "collection": found[1],
              "films": [{"id": f.id, "title": f.title, "year": f.year} for f in parts]}
    return f"Complete {found[1]}", params, len(parts)


# --------------------------------------------------------------------------- progress
def _watched(archive: list[dict]) -> list[dict]:
    return [e for e in archive if e.get("status") == "watched"]


def _decade(year: str) -> int | None:
    return (int(year) // 10) * 10 if str(year).isdigit() and len(str(year)) == 4 else None


def progress(quest: dict, archive: list[dict]) -> tuple[int, int, list[str]]:
    """(done, target, labels of what counted)."""
    kind, params, target = quest["kind"], quest.get("params") or {}, int(quest["target"])
    watched = _watched(archive)
    matched: list[str] = []
    if kind == "genre":
        want = str(params.get("genre", "")).lower()
        matched = [e["title"] for e in watched if want in {g.lower() for g in (e.get("meta") or {}).get("genres", [])}]
    elif kind in ("director", "collection"):
        ids = {int(f["id"]) for f in params.get("films", [])}
        matched = [e["title"] for e in watched if int((e.get("meta") or {}).get("tmdb_id") or 0) in ids]
    elif kind == "decades":
        decades = {_decade(e.get("year", "")) for e in watched} - {None}
        matched = [f"{d}s" for d in sorted(decades)]
    elif kind == "international":
        langs = {(e.get("meta") or {}).get("language", "") for e in watched} - {"", "en"}
        matched = [LANGUAGE_NAMES.get(code, code) for code in sorted(langs)]
    return min(len(matched), target), target, matched


def is_complete(quest: dict, archive: list[dict]) -> bool:
    done, target, _ = progress(quest, archive)
    return done >= target


def remaining_films(quest: dict, archive: list[dict]) -> list[dict]:
    """For director/collection quests: the real films not yet watched."""
    watched_ids = {int((e.get("meta") or {}).get("tmdb_id") or 0) for e in _watched(archive)}
    return [f for f in (quest.get("params") or {}).get("films", []) if int(f["id"]) not in watched_ids]


def discover_kwargs(quest: dict, archive: list[dict], genre_ids_by_name: dict[str, int]) -> dict | None:
    """Arguments for metadata.discover_page that surface films which would advance this quest."""
    kind, params = quest["kind"], quest.get("params") or {}
    if kind == "genre":
        gid = genre_ids_by_name.get(str(params.get("genre", "")).lower())
        return {"kind": "filtered", "genre_ids": (gid,), "sort": "vote_average.desc"} if gid else None
    if kind == "decades":
        have = {_decade(e.get("year", "")) for e in _watched(archive)}
        for decade in range(2020, 1950, -10):
            if decade not in have:
                return {"kind": "filtered", "year_from": decade, "year_to": decade + 9, "sort": "vote_average.desc"}
        return None
    if kind == "international":
        have = {(e.get("meta") or {}).get("language", "") for e in _watched(archive)}
        for code in INTERNATIONAL_SUGGESTIONS:
            if code not in have:
                return {"kind": "filtered", "language": code, "sort": "vote_average.desc"}
        return None
    return None
