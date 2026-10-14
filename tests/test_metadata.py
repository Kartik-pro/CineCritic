import pytest

from cinecritic import metadata
from cinecritic.errors import AppError, ErrorCategory as C
from cinecritic.metadata import (
    Candidate, check_connection, choose_candidate, fetch_details, fetch_recommendations,
    normalize_title, parse_title_year, search_movies,
)

KEY = "0123456789abcdef0123456789abcdef"


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None, bad_json=False):
        self.status_code, self._payload, self.headers, self._bad = status, payload or {}, headers or {}, bad_json

    def json(self):
        if self._bad:
            raise ValueError("no json")
        return self._payload


def setup_function(_):
    metadata.clear_cache()


def test_parse_and_normalize():
    assert parse_title_year("Oppenheimer (2023)") == ("Oppenheimer", "2023")
    assert parse_title_year("Heat") == ("Heat", "")
    assert normalize_title("The  Town!") == normalize_title("town")


def test_search_uses_year_filter_caches_and_sends_key_as_param(monkeypatch):
    seen = []

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.append((url, dict(params), headers))
        return FakeResponse(payload={"results": [
            {"id": 1, "title": "Heat", "release_date": "1995-12-15", "popularity": 50, "poster_path": "/h.jpg"}]})

    monkeypatch.setattr(metadata.requests, "get", fake_get)
    out = search_movies("Heat", KEY, "1995")
    assert out[0].id == 1 and out[0].poster_url.endswith("/w342/h.jpg")
    assert seen[0][1]["year"] == "1995" and seen[0][1]["api_key"] == KEY
    search_movies("heat", KEY, "1995")
    assert len(seen) == 1                                     # cached


def test_v4_token_uses_bearer_header(monkeypatch):
    seen = {}
    monkeypatch.setattr(metadata.requests, "get", lambda url, params=None, headers=None, timeout=None:
                        seen.update(h=headers, p=params) or FakeResponse(payload={"results": []}))
    search_movies("x", "eyJhbGciOi.payload.sig", "")
    assert seen["h"]["Authorization"].startswith("Bearer ") and "api_key" not in seen["p"]


def test_choose_candidate_handles_remakes_and_year():
    cands = [
        Candidate(1, "Dune", "2021", 90), Candidate(2, "Dune", "1984", 30),
        Candidate(3, "Dune: Part Two", "2024", 99),
    ]
    sel = choose_candidate(cands, "Dune", "")
    assert sel.best.id == 1 and [c.id for c in sel.alternatives] == [2]
    assert choose_candidate(cands, "Dune", "1984").best.id == 2
    assert choose_candidate([], "x") is None


def test_details_parse_cast_rating_and_cache(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        return FakeResponse(payload={
            "title": "Heat", "release_date": "1995-12-15", "runtime": 170, "vote_average": 7.9,
            "vote_count": 9000, "tagline": "A study in obsession", "genres": [{"name": "Crime"}],
            "poster_path": "/p.jpg", "backdrop_path": "/b.jpg",
            "credits": {"cast": [{"name": "Al Pacino", "character": "Hanna"}],
                        "crew": [{"job": "Director", "name": "Michael Mann"}]}})

    monkeypatch.setattr(metadata.requests, "get", fake_get)
    meta, hit = fetch_details(949, KEY)
    assert not hit and meta.tmdb_id == 949 and meta.director == "Michael Mann"
    assert meta.runtime == "2h 50m" and meta.rating == 7.9 and meta.cast[0] == ("Al Pacino", "Hanna")
    assert fetch_details(949, KEY)[1] is True and len(calls) == 1


@pytest.mark.parametrize("status,category,retryable", [
    (401, C.AUTH, False), (404, C.TMDB, False), (429, C.RATE_LIMIT, True), (503, C.TMDB, True),
])
def test_http_failures_are_classified(monkeypatch, status, category, retryable):
    monkeypatch.setattr(metadata.requests, "get", lambda *a, **k: FakeResponse(status=status, headers={"Retry-After": "2"}))
    with pytest.raises(AppError) as info:
        check_connection(KEY)
    assert info.value.category is category and info.value.retryable is retryable
    assert KEY not in info.value.message and KEY not in info.value.technical


def test_network_errors_never_leak_the_key(monkeypatch):
    def boom(*a, **k):
        raise metadata.requests.ConnectionError(f"HTTPSConnectionPool: /3/search/movie?api_key={KEY}&query=x")

    monkeypatch.setattr(metadata.requests, "get", boom)
    with pytest.raises(AppError) as info:
        search_movies("Heat", KEY)
    assert info.value.category is C.NETWORK and info.value.retryable
    assert KEY not in info.value.message and KEY not in info.value.technical


def test_unreadable_json_is_malformed(monkeypatch):
    monkeypatch.setattr(metadata.requests, "get", lambda *a, **k: FakeResponse(bad_json=True))
    with pytest.raises(AppError) as info:
        fetch_recommendations(1, KEY, 4)
    assert info.value.category is C.MALFORMED
