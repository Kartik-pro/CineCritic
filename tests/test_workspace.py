import json

import pytest

from cinecritic.storage.workspace import Workspace


def test_archive_crud_validation_and_filters():
    ws = Workspace()
    ws.upsert_archive("tmdb:1", "Heat", year="1995", status="watched", rating=9, favorite=True,
                      meta={"genres": ["Crime"]})
    ws.upsert_archive("tmdb:2", "Alien", year="1979", status="planned")
    ws.upsert_archive("tmdb:2", "Alien", notes="Rewatch soon")      # partial update keeps other fields
    e = ws.get_archive_entry("tmdb:2")
    assert e["status"] == "planned" and e["notes"] == "Rewatch soon" and e["rating"] is None
    assert [r["title"] for r in ws.list_archive(status="watched")] == ["Heat"]
    assert [r["title"] for r in ws.list_archive(favorite=True)] == ["Heat"]
    assert [r["title"] for r in ws.list_archive(query="rewatch")] == ["Alien"]
    assert [r["title"] for r in ws.list_archive(sort="title")] == ["Alien", "Heat"]
    assert ws.list_archive(sort="rating")[0]["title"] == "Heat"
    with pytest.raises(ValueError):
        ws.upsert_archive("x", "X", status="seen")
    with pytest.raises(ValueError):
        ws.upsert_archive("x", "X", rating=11)
    assert ws.delete_archive("tmdb:1") and not ws.delete_archive("tmdb:1")


def test_returned_entries_are_copies():
    ws = Workspace()
    ws.upsert_archive("k", "T", meta={"a": 1})
    ws.get_archive_entry("k")["meta"]["a"] = 99
    assert ws.get_archive_entry("k")["meta"]["a"] == 1


def test_analysis_versions_latest_and_cap():
    ws = Workspace()
    for i in range(25):
        ws.save_analysis("tmdb:1", {"n": i}, model_id="m", spoiler_level="none" if i % 2 else "full", prompt_version="4")
    versions = ws.analysis_versions("tmdb:1")
    assert len(versions) == 20 and versions[0]["version"] == 25
    assert ws.latest_analysis("tmdb:1")["payload"] == {"n": 24}
    assert ws.latest_analysis("tmdb:1", spoiler_level="none")["payload"] == {"n": 23}
    assert ws.latest_analysis("tmdb:1", prompt_version="3") is None
    assert ws.get_analysis("tmdb:1", 25)["payload"] == {"n": 24}
    assert ws.get_analysis("tmdb:1", 1) is None          # trimmed away


def test_chats_quests_usage_and_runs():
    ws = Workspace()
    ws.add_chat("", "user", "hi"); ws.add_chat("", "assistant", "hello"); ws.add_chat("f", "user", "x")
    assert [m["role"] for m in ws.list_chats("")] == ["user", "assistant"]
    assert ws.clear_chats("f") == 1 and ws.clear_chats() == 2
    with pytest.raises(ValueError):
        ws.add_chat("", "system", "no")
    q = ws.create_quest("genre", "Watch 3", {"genre": "Crime"}, 3)
    ws.complete_quest(q)
    assert ws.list_quests()[0]["completed_at"] and ws.delete_quest(q)
    ws.record_usage(provider="Gemini", model="m", task="analysis", ok=True, latency_ms=5)
    assert len(ws.usage_events()) == 1 and ws.usage_events(since=9e12) == []
    ws.log_run(run_id="a", kind="analysis", label="Heat", status="completed", duration_s=1, model="m", retries=0,
               error_category="", stages=[])
    ws.log_run(run_id="a", kind="analysis", label="Heat", status="failed", duration_s=2, model="m", retries=1,
               error_category="auth", stages=[])
    assert len(ws.recent_runs()) == 1 and ws.recent_runs()[0]["status"] == "failed"


def test_backup_roundtrip_contains_no_secrets_and_restores_data():
    ws = Workspace()
    ws.set_pref("preferences", {"spoiler_level": "light"})
    ws.upsert_archive("tmdb:1", "Heat", year="1995", status="watched", rating=9, meta={"tmdb_id": 1})
    ws.save_analysis("tmdb:1", {"critique": {}}, model_id="Gemini:x", prompt_version="4")
    ws.add_chat("tmdb:1", "user", "q")
    q = ws.create_quest("decades", "Decades", {}, 5)
    ws.complete_quest(q)
    ws.record_usage(provider="Gemini", model="m", task="analysis", ok=True, latency_ms=5)
    text = ws.export_json()
    assert "usage" not in text and "api_key" not in text.lower()
    other = Workspace()
    counts = other.import_data(text)
    assert counts == {"archive": 1, "analyses": 1, "chats": 1, "quests": 1}
    assert other.get_pref("preferences") == {"spoiler_level": "light"}
    assert other.get_archive_entry("tmdb:1")["rating"] == 9 and other.list_quests()[0]["completed_at"]


def test_import_rejects_garbage_and_oversized_or_foreign_files():
    ws = Workspace()
    for bad in ("not json", json.dumps({"format": "other"}), json.dumps([1]), b"x" * 6_000_000):
        with pytest.raises(ValueError):
            ws.import_data(bad)
    ok = {"format": "cinecritic-backup", "archive": [{"film_key": "k", "title": "T", "status": "hacked"},
                                                     {"film_key": "k2", "title": "T2", "status": "watched"}],
          "chats": {"": [{"role": "system", "content": "x"}]}}
    assert ws.import_data(ok)["archive"] == 1 and ws.import_data(ok)["chats"] == 0


def test_clear_all_resets_everything():
    ws = Workspace()
    ws.upsert_archive("k", "T")
    ws.clear_all()
    assert ws.counts()["archive"] == 0
