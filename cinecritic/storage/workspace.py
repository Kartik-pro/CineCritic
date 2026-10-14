"""In-session workspace: archive, analyses, chats, quests, preferences, usage and run history.

There is NO database. A Workspace is a plain Python object kept in `st.session_state`, so it is
private to one browser session (no cross-user leakage) and disappears when the session ends.
To keep data between visits, users download a JSON backup and restore it later
(`export_data` / `import_data`). Backups never contain API keys, prompts or provider payloads.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from typing import Any

from ..config import MAX_ARCHIVE, MAX_BACKUP_BYTES, MAX_RUNS, MAX_USAGE_EVENTS

STATUSES = ("watched", "planned", "watching")
MAX_TEXT = 4000
MAX_VERSIONS_PER_FILM = 20
MAX_CHATS_PER_FILM = 200
BACKUP_FORMAT = "cinecritic-backup"
BACKUP_VERSION = 3


def _clip(value: Any, n: int = MAX_TEXT) -> str:
    return str(value or "")[:n]


class Workspace:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.prefs: dict[str, Any] = {}
        self.archive: dict[str, dict] = {}
        self.analyses: dict[str, list[dict]] = {}          # film_key -> versions (oldest first)
        self.chats: dict[str, list[dict]] = {}              # film_key ('' = general) -> messages
        self.quests: list[dict] = []
        self.usage: deque[dict] = deque(maxlen=MAX_USAGE_EVENTS)
        self.runs: deque[dict] = deque(maxlen=MAX_RUNS)
        self._next_quest = 1
        self.created_at = time.time()

    # ------------------------------------------------------------------ preferences
    def get_pref(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.prefs.get(key, default)

    def set_pref(self, key: str, value: Any) -> None:
        with self._lock:
            self.prefs[_clip(key, 80)] = value

    # ------------------------------------------------------------------ archive
    def upsert_archive(self, film_key: str, title: str, *, year: str = "", status: str | None = None,
                       rating: float | None | str = "keep", review: str | None = None, notes: str | None = None,
                       favorite: bool | None = None, meta: dict | None = None) -> None:
        if not film_key or not title:
            raise ValueError("film_key and title are required")
        if status is not None and status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        if rating not in ("keep", None):
            rating = float(rating)
            if not 0 <= rating <= 10:
                raise ValueError("rating must be between 0 and 10")
        now = time.time()
        with self._lock:
            row = self.archive.get(film_key)
            if row is None:
                if len(self.archive) >= MAX_ARCHIVE:
                    raise ValueError("Archive is full. Remove a film first.")
                self.archive[film_key] = {
                    "film_key": film_key, "title": _clip(title, 200), "year": _clip(year, 8),
                    "status": status or "planned", "rating": None if rating == "keep" else rating,
                    "review": _clip(review), "notes": _clip(notes), "favorite": bool(favorite),
                    "meta": dict(meta or {}), "added_at": now, "updated_at": now}
                return
            row["title"] = _clip(title, 200) or row["title"]
            if year:
                row["year"] = _clip(year, 8)
            if status:
                row["status"] = status
            if rating != "keep":
                row["rating"] = rating
            if review is not None:
                row["review"] = _clip(review)
            if notes is not None:
                row["notes"] = _clip(notes)
            if favorite is not None:
                row["favorite"] = bool(favorite)
            if meta is not None:
                row["meta"] = dict(meta)
            row["updated_at"] = now

    def get_archive_entry(self, film_key: str) -> dict | None:
        with self._lock:
            row = self.archive.get(film_key)
            return json.loads(json.dumps(row)) if row else None

    def list_archive(self, *, status: str | None = None, favorite: bool | None = None, query: str = "",
                     sort: str = "updated") -> list[dict]:
        with self._lock:
            rows = [json.loads(json.dumps(r)) for r in self.archive.values()]
        if status:
            rows = [r for r in rows if r["status"] == status]
        if favorite is not None:
            rows = [r for r in rows if r["favorite"] == favorite]
        q = query.strip().lower()
        if q:
            rows = [r for r in rows if q in r["title"].lower() or q in r["notes"].lower() or q in r["review"].lower()]
        keys = {
            "updated": (lambda r: r["updated_at"], True), "added": (lambda r: r["added_at"], True),
            "title": (lambda r: r["title"].lower(), False), "year": (lambda r: r["year"], True),
            "rating": (lambda r: (r["rating"] is not None, r["rating"] or 0), True),
        }
        fn, rev = keys.get(sort, keys["updated"])
        return sorted(rows, key=fn, reverse=rev)

    def delete_archive(self, film_key: str) -> bool:
        with self._lock:
            return self.archive.pop(film_key, None) is not None

    # ------------------------------------------------------------------ analyses (versioned)
    def save_analysis(self, film_key: str, payload: dict, *, model_id: str = "", spoiler_level: str = "none",
                      prompt_version: str = "") -> int:
        with self._lock:
            versions = self.analyses.setdefault(film_key, [])
            number = (versions[-1]["version"] + 1) if versions else 1
            versions.append({"version": number, "created_at": time.time(), "model_id": _clip(model_id, 120),
                             "spoiler_level": spoiler_level, "prompt_version": prompt_version,
                             "payload": payload})
            del versions[:-MAX_VERSIONS_PER_FILM]
            return number

    def latest_analysis(self, film_key: str, *, spoiler_level: str | None = None,
                        prompt_version: str | None = None) -> dict | None:
        with self._lock:
            for item in reversed(self.analyses.get(film_key, [])):
                if spoiler_level and item["spoiler_level"] != spoiler_level:
                    continue
                if prompt_version and item["prompt_version"] != prompt_version:
                    continue
                return item
        return None

    def analysis_versions(self, film_key: str) -> list[dict]:
        with self._lock:
            return [{k: v for k, v in item.items() if k != "payload"}
                    for item in reversed(self.analyses.get(film_key, []))]

    def get_analysis(self, film_key: str, version: int) -> dict | None:
        with self._lock:
            return next((i for i in self.analyses.get(film_key, []) if i["version"] == version), None)

    def list_latest_analyses(self) -> list[dict]:
        with self._lock:
            latest = [dict(v[-1], film_key=k) for k, v in self.analyses.items() if v]
        return sorted(latest, key=lambda i: i["created_at"], reverse=True)

    def delete_analyses(self, film_key: str) -> int:
        with self._lock:
            return len(self.analyses.pop(film_key, []))

    # ------------------------------------------------------------------ chats
    def add_chat(self, film_key: str, role: str, content: str) -> None:
        if role not in ("user", "assistant"):
            raise ValueError("role must be user or assistant")
        with self._lock:
            msgs = self.chats.setdefault(film_key or "", [])
            msgs.append({"role": role, "content": _clip(content, 8000), "created_at": time.time()})
            del msgs[:-MAX_CHATS_PER_FILM]

    def list_chats(self, film_key: str = "", limit: int = 100) -> list[dict]:
        with self._lock:
            return list(self.chats.get(film_key or "", []))[-limit:]

    def clear_chats(self, film_key: str | None = None) -> int:
        with self._lock:
            if film_key is None:
                n = sum(len(v) for v in self.chats.values())
                self.chats.clear()
                return n
            return len(self.chats.pop(film_key, []))

    # ------------------------------------------------------------------ quests
    def create_quest(self, kind: str, title: str, params: dict, target: int) -> int:
        with self._lock:
            qid = self._next_quest
            self._next_quest += 1
            self.quests.append({"id": qid, "kind": _clip(kind, 30), "title": _clip(title, 160),
                                "params": dict(params), "target": max(1, int(target)),
                                "created_at": time.time(), "completed_at": None})
            return qid

    def list_quests(self) -> list[dict]:
        with self._lock:
            return sorted((dict(q) for q in self.quests),
                          key=lambda q: (q["completed_at"] is not None, -q["id"]))

    def complete_quest(self, quest_id: int) -> None:
        with self._lock:
            for q in self.quests:
                if q["id"] == quest_id and q["completed_at"] is None:
                    q["completed_at"] = time.time()

    def delete_quest(self, quest_id: int) -> bool:
        with self._lock:
            before = len(self.quests)
            self.quests = [q for q in self.quests if q["id"] != quest_id]
            return len(self.quests) < before

    # ------------------------------------------------------------------ usage + runs
    def record_usage(self, *, provider: str, model: str, task: str, ok: bool, latency_ms: int | None,
                     in_tokens: int | None = None, out_tokens: int | None = None, retries: int = 0,
                     error_category: str = "", error_message: str = "", run_id: str = "", fallback: bool = False,
                     stages: list | None = None, ts: float | None = None) -> None:
        event = {"ts": ts or time.time(), "provider": _clip(provider, 40), "model": _clip(model, 120),
                 "task": _clip(task, 30), "ok": bool(ok), "error_category": _clip(error_category, 40),
                 "error_message": _clip(error_message, 300), "latency_ms": latency_ms, "in_tokens": in_tokens,
                 "out_tokens": out_tokens, "retries": retries, "run_id": _clip(run_id, 16),
                 "fallback": bool(fallback), "stages": stages or []}
        with self._lock:
            self.usage.append(event)

    def usage_events(self, since: float | None = None) -> list[dict]:
        with self._lock:
            return [dict(e) for e in reversed(self.usage) if e["ts"] >= (since or 0)]

    def log_run(self, *, run_id: str, kind: str, label: str, status: str, duration_s: float, model: str,
                retries: int, error_category: str, stages: list) -> None:
        with self._lock:
            self.runs = deque((r for r in self.runs if r["run_id"] != run_id), maxlen=MAX_RUNS)
            self.runs.append({"run_id": run_id, "ts": time.time(), "kind": kind, "label": _clip(label, 60),
                              "status": status, "duration_s": duration_s, "model": _clip(model, 120),
                              "retries": retries, "error_category": error_category, "stages": stages})

    def recent_runs(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return [dict(r) for r in reversed(self.runs)][:limit]

    # ------------------------------------------------------------------ backup / restore
    def counts(self) -> dict[str, int]:
        with self._lock:
            return {"archive": len(self.archive), "analyses": sum(len(v) for v in self.analyses.values()),
                    "chats": sum(len(v) for v in self.chats.values()), "quests": len(self.quests),
                    "usage_events": len(self.usage), "runs": len(self.runs)}

    def export_data(self) -> dict:
        """Portable JSON snapshot. Contains no credentials, prompts or usage payloads."""
        with self._lock:
            return json.loads(json.dumps({
                "format": BACKUP_FORMAT, "version": BACKUP_VERSION, "exported_at": time.time(),
                "prefs": self.prefs, "archive": list(self.archive.values()), "analyses": self.analyses,
                "chats": self.chats, "quests": self.quests}, default=str))

    def export_json(self) -> str:
        return json.dumps(self.export_data(), ensure_ascii=False, indent=2)

    def import_data(self, data: dict | str | bytes) -> dict[str, int]:
        """Merge a backup into this workspace. Only whitelisted fields are read; sizes are bounded."""
        if isinstance(data, (str, bytes)):
            if len(data) > MAX_BACKUP_BYTES:
                raise ValueError("Backup file is too large.")
            try:
                data = json.loads(data)
            except ValueError:
                raise ValueError("That file is not valid JSON.") from None
        if not isinstance(data, dict) or data.get("format") != BACKUP_FORMAT:
            raise ValueError("This file is not a CineCritic backup.")
        counts = {"archive": 0, "analyses": 0, "chats": 0, "quests": 0}
        with self._lock:
            prefs = data.get("prefs")
            if isinstance(prefs, dict):
                self.prefs.update({_clip(k, 80): v for k, v in prefs.items()})
            for row in (data.get("archive") or [])[:MAX_ARCHIVE]:
                if (isinstance(row, dict) and row.get("film_key") and row.get("title")
                        and row.get("status") in STATUSES):
                    try:
                        self.upsert_archive(
                            row["film_key"], row["title"], year=row.get("year", ""), status=row["status"],
                            rating=row.get("rating"), review=row.get("review", ""), notes=row.get("notes", ""),
                            favorite=bool(row.get("favorite")),
                            meta=row.get("meta") if isinstance(row.get("meta"), dict) else {})
                        counts["archive"] += 1
                    except ValueError:
                        continue
            for film_key, versions in (data.get("analyses") or {}).items():
                if not isinstance(versions, list):
                    continue
                for item in versions[-MAX_VERSIONS_PER_FILM:]:
                    if isinstance(item, dict) and isinstance(item.get("payload"), dict):
                        self.save_analysis(_clip(film_key, 120), item["payload"], model_id=item.get("model_id", ""),
                                           spoiler_level=item.get("spoiler_level", "none"),
                                           prompt_version=str(item.get("prompt_version", "")))
                        counts["analyses"] += 1
            for film_key, msgs in (data.get("chats") or {}).items():
                for m in (msgs if isinstance(msgs, list) else [])[-MAX_CHATS_PER_FILM:]:
                    if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content"):
                        self.add_chat(_clip(film_key, 120), m["role"], m["content"])
                        counts["chats"] += 1
            for q in data.get("quests") or []:
                if isinstance(q, dict) and q.get("kind") and q.get("title"):
                    qid = self.create_quest(q["kind"], q["title"], q.get("params") if isinstance(q.get("params"), dict) else {},
                                            int(q.get("target") or 1))
                    if q.get("completed_at"):
                        self.complete_quest(qid)
                    counts["quests"] += 1
        return counts

    def clear_all(self) -> None:
        with self._lock:
            self.__init__()  # type: ignore[misc]
