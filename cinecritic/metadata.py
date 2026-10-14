"""TMDB integration: search, ID-based details, credits, ratings, images and recommendations.

All functions raise a classified `AppError` (never a raw requests exception, which would
carry the request URL and therefore the key). Retries/backoff are applied by the caller
through `pipeline.call_with_retries`, so every attempt is visible in the pipeline log.

TMDB v3 API keys (32 hex chars) and v4 read-access tokens (start with "eyJ") are both
supported. TMDB requires attribution, which the footer shows when TMDB data is used.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from .cache import TTLCache
from .config import LISTING_CACHE_TTL_S, META_CACHE_MAX, META_CACHE_TTL_S
from .errors import AppError, ErrorCategory, HTTPFailure, classify

API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"
TIMEOUT_S = 8

_CACHE = TTLCache(META_CACHE_TTL_S, META_CACHE_MAX)
_LIST_CACHE = TTLCache(LISTING_CACHE_TTL_S, 256)   # popular/trending/search pages (public data only)
_YEAR_RE = re.compile(r"^(.*?)[\s]*\((\d{4})\)\s*$")


@dataclass(frozen=True)
class Candidate:
    id: int
    title: str
    year: str = ""
    popularity: float = 0.0
    overview: str = ""
    poster_url: str = ""
    rating: float | None = None                 # TMDB audience average (0-10) when it has votes
    votes: int = 0
    genre_ids: tuple[int, ...] = ()
    language: str = ""                          # original language code, e.g. "en"


@dataclass(frozen=True)
class Page:
    items: tuple[Candidate, ...]
    page: int = 1
    total_pages: int = 1
    total_results: int = 0


@dataclass(frozen=True)
class MovieMeta:
    title: str
    tmdb_id: int = 0
    year: str = ""
    runtime: str = ""
    genres: tuple[str, ...] = ()
    director: str = ""
    cinematographer: str = ""
    composer: str = ""
    cast: tuple[tuple[str, str], ...] = ()      # (actor, character)
    overview: str = ""
    tagline: str = ""
    rating: float | None = None                 # TMDB audience average, 0-10
    votes: int = 0
    poster_url: str = ""
    backdrop_url: str = ""
    source: str = "TMDB"
    language: str = ""
    collection_id: int = 0                      # franchise / collection TMDB ID, when it belongs to one
    collection_name: str = ""


@dataclass(frozen=True)
class Selection:
    best: Candidate
    alternatives: tuple[Candidate, ...] = ()    # same-title remakes / duplicates


# --------------------------------------------------------------------------- title helpers
def parse_title_year(text: str) -> tuple[str, str]:
    """'Oppenheimer (2023)' -> ('Oppenheimer', '2023'); otherwise (text, '')."""
    match = _YEAR_RE.match(text.strip())
    if match and match.group(1):
        return match.group(1).strip(), match.group(2)
    return text.strip(), ""


def normalize_title(text: str) -> str:
    """Stable key for caching/dedup: lowercase, alphanumerics only, no leading article."""
    title, _ = parse_title_year(text)
    cleaned = re.sub(r"[^a-z0-9 ]+", "", title.lower())
    cleaned = re.sub(r"^(the|a|an) ", "", cleaned.strip())
    return re.sub(r"\s+", " ", cleaned).strip()


# --------------------------------------------------------------------------- HTTP
def _get(path: str, params: dict, key: str) -> dict:
    headers: dict[str, str] = {}
    params = dict(params)
    if key.startswith("eyJ"):  # v4 read-access token
        headers["Authorization"] = f"Bearer {key}"
    else:                       # v3 api key
        params["api_key"] = key
    try:
        response = requests.get(f"{API}{path}", params=params, headers=headers, timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        raise classify(exc, source="tmdb", secrets=[key]) from None
    if response.status_code >= 400:
        retry_after = response.headers.get("Retry-After") if response.headers else None
        raise classify(HTTPFailure(response.status_code, retry_after), source="tmdb", secrets=[key])
    try:
        return response.json()
    except ValueError:
        raise AppError(ErrorCategory.MALFORMED, "TMDB returned an unreadable response. Retry shortly.",
                       retryable=True, source="tmdb") from None


def _img(path: str | None, size: str) -> str:
    return f"{IMG}/{size}{path}" if path else ""


def _runtime(minutes: int | None) -> str:
    if not minutes:
        return ""
    return f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"


def _crew(credits: dict, *jobs: str) -> str:
    for person in credits.get("crew", []):
        if person.get("job") in jobs and person.get("name"):
            return person["name"]
    return ""


def _candidate(item: dict) -> Candidate | None:
    if not item.get("id") or not item.get("title"):
        return None
    return Candidate(
        id=int(item["id"]),
        title=item["title"],
        year=(item.get("release_date") or "")[:4],
        popularity=float(item.get("popularity") or 0),
        overview=item.get("overview") or "",
        poster_url=_img(item.get("poster_path"), "w342"),
        rating=round(float(item["vote_average"]), 1) if item.get("vote_count") and item.get("vote_average") else None,
        votes=int(item.get("vote_count") or 0),
        genre_ids=tuple(int(g) for g in item.get("genre_ids") or [] if isinstance(g, int)),
        language=str(item.get("original_language") or ""),
    )


# --------------------------------------------------------------------------- public API
def search_movies(title: str, key: str, year: str = "") -> list[Candidate]:
    """Search by title with optional release-year filter. Cached per (title, year)."""
    cache_key = ("search", normalize_title(title), year)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached
    params = {"query": title, "include_adult": "false"}
    if year:
        params["year"] = year
    results = _get("/search/movie", params, key).get("results") or []
    candidates = [c for c in map(_candidate, results) if c]
    if candidates:  # never cache empty/failed lookups
        _CACHE.set(cache_key, candidates)
    return candidates


def choose_candidate(candidates: list[Candidate], title: str, year: str = "") -> Selection | None:
    """Pick the intended film and surface same-title alternatives (remakes, duplicates)."""
    if not candidates:
        return None
    wanted = normalize_title(title)

    def score(c: Candidate) -> tuple:
        return (normalize_title(c.title) == wanted, bool(year) and c.year == year, c.popularity)

    best = max(candidates, key=score)
    alts = sorted(
        (c for c in candidates
         if c.id != best.id and normalize_title(c.title) == normalize_title(best.title) and c.year != best.year),
        key=lambda c: c.year, reverse=True,
    )[:4]
    return Selection(best, tuple(alts))


def fetch_details(movie_id: int, key: str) -> tuple[MovieMeta, bool]:
    """Full details + credits for a TMDB movie ID. Returns (meta, served_from_cache)."""
    cache_key = ("details", movie_id)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached, True
    detail = _get(f"/movie/{movie_id}", {"append_to_response": "credits"}, key)
    credits = detail.get("credits") or {}
    cast = tuple(
        (p["name"], p.get("character") or "")
        for p in (credits.get("cast") or [])[:6] if p.get("name")
    )
    votes = int(detail.get("vote_count") or 0)
    meta = MovieMeta(
        title=detail.get("title") or "",
        tmdb_id=movie_id,
        year=(detail.get("release_date") or "")[:4],
        runtime=_runtime(detail.get("runtime")),
        genres=tuple(g["name"] for g in detail.get("genres", []) if g.get("name")),
        director=_crew(credits, "Director"),
        cinematographer=_crew(credits, "Director of Photography"),
        composer=_crew(credits, "Original Music Composer", "Composer"),
        cast=cast,
        overview=detail.get("overview") or "",
        tagline=detail.get("tagline") or "",
        rating=round(float(detail["vote_average"]), 1) if votes and detail.get("vote_average") else None,
        votes=votes,
        poster_url=_img(detail.get("poster_path"), "w500"),
        backdrop_url=_img(detail.get("backdrop_path"), "w1280"),
        language=str(detail.get("original_language") or ""),
        collection_id=int((detail.get("belongs_to_collection") or {}).get("id") or 0),
        collection_name=str((detail.get("belongs_to_collection") or {}).get("name") or ""),
    )
    _CACHE.set(cache_key, meta)
    return meta, False


def fetch_recommendations(movie_id: int, key: str, n: int) -> list[Candidate]:
    """TMDB's own 'recommendations' for a film (used when the AI step is unavailable)."""
    results = _get(f"/movie/{movie_id}/recommendations", {}, key).get("results") or []
    return [c for c in map(_candidate, results) if c][:n]


def check_connection(key: str) -> None:
    """Cheapest authenticated call; raises a classified AppError on failure."""
    _get("/configuration", {}, key)


def clear_cache() -> None:
    _CACHE.clear()
    _LIST_CACHE.clear()


def cache_stats() -> dict[str, int]:
    return {"details_entries": len(_CACHE), "details_hits": _CACHE.hits, "details_misses": _CACHE.misses,
            "listing_entries": len(_LIST_CACHE), "listing_hits": _LIST_CACHE.hits, "listing_misses": _LIST_CACHE.misses}


# --------------------------------------------------------------------------- genres, listings, search pages
def genre_map(key: str) -> dict[int, str]:
    """TMDB genre id -> name (cached for a day)."""
    cache_key = ("genres",)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached
    genres = _get("/genre/movie/list", {}, key).get("genres") or []
    mapping = {int(g["id"]): g["name"] for g in genres if g.get("id") and g.get("name")}
    if mapping:
        _CACHE.set(cache_key, mapping)
    return mapping


def _page(data: dict, page: int) -> Page:
    items = tuple(c for c in map(_candidate, data.get("results") or []) if c)
    return Page(items, int(data.get("page") or page), max(1, min(int(data.get("total_pages") or 1), 500)),
                int(data.get("total_results") or len(items)))


LISTING_KINDS = {
    "popular": "/movie/popular",
    "trending": "/trending/movie/week",
    "top_rated": "/movie/top_rated",
    "now_playing": "/movie/now_playing",
    "filtered": "/discover/movie",
}
SORTS = {"Popularity": "popularity.desc", "Rating": "vote_average.desc", "Newest": "primary_release_date.desc",
         "Oldest": "primary_release_date.asc"}


def discover_page(key: str, kind: str = "popular", page: int = 1, *, genre_ids: tuple[int, ...] = (),
                  year_from: int | None = None, year_to: int | None = None, language: str = "",
                  sort: str = "popularity.desc") -> Page:
    """Real TMDB listings. `filtered` uses /discover with genre/year/language filters."""
    path = LISTING_KINDS.get(kind)
    if path is None:
        raise AppError(ErrorCategory.INVALID_INPUT, "Unknown listing type.")
    page = max(1, min(int(page), 500))
    params: dict = {"page": page, "include_adult": "false"}
    if kind == "filtered":
        params["sort_by"] = sort
        if sort.startswith("vote_average"):
            params["vote_count.gte"] = 300          # avoid one-vote 10/10 films topping the list
        if genre_ids:
            params["with_genres"] = ",".join(str(g) for g in genre_ids)    # AND semantics
        if year_from:
            params["primary_release_date.gte"] = f"{int(year_from)}-01-01"
        if year_to:
            params["primary_release_date.lte"] = f"{int(year_to)}-12-31"
        if language:
            params["with_original_language"] = language
    cache_key = ("list", kind, tuple(sorted(params.items())))
    cached = _LIST_CACHE.get(cache_key)
    if cached is not None:
        return cached
    result = _page(_get(path, params, key), page)
    if result.items:
        _LIST_CACHE.set(cache_key, result)
    return result


def search_page(title: str, key: str, page: int = 1, year: str = "") -> Page:
    """One page of title search results (cached). Used by Smart Movie Search."""
    page = max(1, min(int(page), 500))
    cache_key = ("search_page", normalize_title(title), year, page)
    cached = _LIST_CACHE.get(cache_key)
    if cached is not None:
        return cached
    params = {"query": title, "include_adult": "false", "page": page}
    if year:
        params["year"] = year
    result = _page(_get("/search/movie", params, key), page)
    if result.items:
        _LIST_CACHE.set(cache_key, result)
    return result


def filter_sort(items, *, genre_ids: tuple[int, ...] = (), min_rating: float = 0.0, language: str = "",
                year_from: int | None = None, year_to: int | None = None, sort: str = "Relevance") -> list[Candidate]:
    """Client-side refinement of already-fetched results (no extra requests)."""
    out = []
    for c in items:
        if genre_ids and not set(genre_ids) <= set(c.genre_ids):
            continue
        if min_rating and (c.rating or 0) < min_rating:
            continue
        if language and c.language != language:
            continue
        year = int(c.year) if c.year.isdigit() else None
        if year_from and (year is None or year < year_from):
            continue
        if year_to and (year is None or year > year_to):
            continue
        out.append(c)
    if sort == "Rating":
        out.sort(key=lambda c: (c.rating or 0, c.votes), reverse=True)
    elif sort == "Newest":
        out.sort(key=lambda c: c.year, reverse=True)
    elif sort == "Oldest":
        out.sort(key=lambda c: c.year or "9999")
    elif sort == "Title":
        out.sort(key=lambda c: c.title.lower())
    elif sort == "Popularity":
        out.sort(key=lambda c: c.popularity, reverse=True)
    return out


def suggest(prefix: str, key: str, limit: int = 6) -> list[Candidate]:
    """Lightweight autocomplete from TMDB (page 1 only, cached). Never calls an LLM."""
    if len(prefix.strip()) < 3:
        return []
    title, year = parse_title_year(prefix)
    return list(search_page(title, key, 1, year).items)[:limit]


# --------------------------------------------------------------------------- people + collections (quests)
def find_director(name: str, key: str) -> tuple[int, str] | None:
    """Best TMDB person match who is known for directing: (person_id, canonical name)."""
    results = _get("/search/person", {"query": name, "include_adult": "false"}, key).get("results") or []
    for p in results:
        if p.get("id") and p.get("name") and p.get("known_for_department") == "Directing":
            return int(p["id"]), p["name"]
    return None


def director_filmography(person_id: int, key: str) -> list[Candidate]:
    """Movies this person directed (released only), newest first."""
    cache_key = ("filmography", person_id)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached
    credits = _get(f"/person/{person_id}/movie_credits", {}, key).get("crew") or []
    seen, films = set(), []
    for item in credits:
        if item.get("job") != "Director" or not item.get("release_date"):
            continue
        cand = _candidate(item)
        if cand and cand.id not in seen:
            seen.add(cand.id)
            films.append(cand)
    films.sort(key=lambda c: c.year, reverse=True)
    if films:
        _CACHE.set(cache_key, films)
    return films


def find_collection(name: str, key: str) -> tuple[int, str] | None:
    results = _get("/search/collection", {"query": name}, key).get("results") or []
    for c in results:
        if c.get("id") and c.get("name"):
            return int(c["id"]), c["name"]
    return None


def collection_parts(collection_id: int, key: str) -> list[Candidate]:
    cache_key = ("collection", collection_id)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached
    parts = _get(f"/collection/{collection_id}", {}, key).get("parts") or []
    films = sorted((c for c in map(_candidate, parts) if c), key=lambda c: c.year or "9999")
    if films:
        _CACHE.set(cache_key, films)
    return films
