"""Observable execution pipeline: stage tracking, event log, retries with backoff.

UI-independent and thread-safe. The worker thread records real events here; the UI only
reads snapshots, so the on-screen status always reflects what actually executed.
"""
from __future__ import annotations

import copy
import logging
import random
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Iterable, Iterator, TypeVar

from .errors import AppError, ErrorCategory, classify, logger, redact

T = TypeVar("T")

MAX_ATTEMPTS = 3          # first try + 2 retries
BASE_DELAY_S = 0.6
MAX_DELAY_S = 8.0
_sleep: Callable[[float], None] = time.sleep  # patched in tests


class Status(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


STATUS_LABELS = {
    Status.PENDING: "Pending",
    Status.RUNNING: "Running",
    Status.COMPLETED: "Completed",
    Status.FAILED: "Failed",
    Status.SKIPPED: "Skipped",
}


@dataclass(frozen=True)
class StageSpec:
    id: str
    label: str
    parallel: bool = False   # runs concurrently with a sibling stage


STAGES: tuple[StageSpec, ...] = (
    StageSpec("search", "Movie search"),
    StageSpec("tmdb", "TMDB data"),
    StageSpec("process", "Data processing"),
    StageSpec("init", "AI model setup", True),
    StageSpec("analysis", "AI analysis", True),
    StageSpec("recommend", "Recommendations", True),
    StageSpec("render", "Result rendering"),
)
DISCOVER_STAGES: tuple[StageSpec, ...] = (
    StageSpec("input", "Request check"),
    StageSpec("init", "AI model setup"),
    StageSpec("recommend", "AI picks"),
    StageSpec("posters", "TMDB posters"),
    StageSpec("render", "Result rendering"),
)
ASK_STAGES: tuple[StageSpec, ...] = (
    StageSpec("input", "Question check"),
    StageSpec("context", "Film context"),
    StageSpec("init", "AI model setup"),
    StageSpec("answer", "AI answer"),
    StageSpec("render", "Result rendering"),
)
BATTLE_STAGES: tuple[StageSpec, ...] = (
    StageSpec("resolve", "Resolve films"),
    StageSpec("data", "Gather analyses"),
    StageSpec("init", "AI model setup"),
    StageSpec("compare", "Compare scores"),
    StageSpec("narrative", "AI write-up"),
    StageSpec("render", "Result rendering"),
)
# kind -> (stages, critical stage ids, primary stage that must complete for a usable result)
STAGE_SETS = {
    "analysis": (STAGES, {"analysis", "init", "search"}, "analysis"),
    "discover": (DISCOVER_STAGES, {"input", "init", "recommend"}, "recommend"),
    "ask": (ASK_STAGES, {"input", "init", "answer"}, "answer"),
    "battle": (BATTLE_STAGES, {"resolve", "data", "compare"}, "compare"),
}
KIND_LABELS = {"analysis": "Film Critique", "discover": "Film Discovery", "ask": "Ask the Critic",
               "battle": "Movie Battle"}


@dataclass
class Stage:
    id: str
    label: str
    parallel: bool = False
    status: Status = Status.PENDING
    started: float | None = None
    ended: float | None = None
    attempts: int = 0
    cached: bool = False
    note: str = ""
    error: AppError | None = None


@dataclass(frozen=True)
class Event:
    t: float
    stage: str
    level: str      # info | warn | error
    message: str


class PipelineRun:
    def __init__(self, query: str, model_id: str = "", clock: Callable[[], float] = time.monotonic,
                 kind: str = "analysis") -> None:
        specs, self._critical, self._primary = STAGE_SETS[kind]
        self.kind = kind
        self.run_id = uuid.uuid4().hex[:8]
        self.query = query
        self.model_id = model_id
        self.started_at = datetime.now(timezone.utc)
        self._clock = clock
        self._t0 = clock()
        self._lock = threading.RLock()
        self.stages: dict[str, Stage] = {s.id: Stage(s.id, s.label, s.parallel) for s in specs}
        self.events: list[Event] = []
        self._finished: float | None = None

    # ---- time
    def _now(self) -> float:
        return self._clock() - self._t0

    def elapsed(self) -> float:
        with self._lock:
            return (self._finished if self._finished is not None else self._now())

    # ---- recording (all messages are scrubbed before storage or logging)
    def event(self, stage: str, level: str, message: str) -> None:
        message = redact(message)
        with self._lock:
            self.events.append(Event(self._now(), stage, level, message))
        log_level = {"info": logging.INFO, "warn": logging.WARNING, "error": logging.ERROR}.get(level, logging.INFO)
        logger.log(log_level, "run=%s stage=%s %s", self.run_id, stage, message)

    def start(self, stage: str, note: str = "") -> None:
        with self._lock:
            s = self.stages[stage]
            s.status = Status.RUNNING
            s.started = s.started if s.started is not None else self._now()
            s.ended = None
            s.attempts = max(s.attempts, 1)
            s.note = note
        self.event(stage, "info", f"started: {self.stages[stage].label}")

    def retrying(self, stage: str, attempt: int, error: AppError, delay: float) -> None:
        with self._lock:
            self.stages[stage].attempts = attempt + 1
        self.event(
            stage, "warn",
            f"attempt {attempt} failed [{error.category.value}] {error.technical[:160]}; retrying in {delay:.1f}s",
        )

    def complete(self, stage: str, note: str = "", cached: bool = False) -> None:
        with self._lock:
            s = self.stages[stage]
            s.status = Status.COMPLETED
            s.started = s.started if s.started is not None else self._now()
            s.ended = self._now()
            s.note, s.cached, s.error = note, cached, None
        self.event(stage, "info", f"completed{' (cached)' if cached else ''}: {note}" if note else "completed")

    def fail(self, stage: str, error: AppError) -> None:
        with self._lock:
            s = self.stages[stage]
            s.status = Status.FAILED
            s.started = s.started if s.started is not None else self._now()
            s.ended = self._now()
            s.error = error
            s.note = error.message
        self.event(stage, "error", f"failed [{error.category.value}] {error.technical[:200]}")

    def skip(self, stage: str, reason: str) -> None:
        with self._lock:
            s = self.stages[stage]
            s.status = Status.SKIPPED
            s.ended = self._now()
            s.note = reason
        self.event(stage, "info", f"skipped: {reason}")

    def finish(self) -> None:
        with self._lock:
            for s in self.stages.values():
                if s.status is Status.PENDING and s.id != "render":
                    s.status, s.note, s.ended = Status.SKIPPED, "Not reached", self._now()
            self._finished = self._now()

    # ---- reading
    def stage(self, stage: str) -> Stage:
        with self._lock:
            return copy.copy(self.stages[stage])

    def view(self) -> tuple[list[Stage], list[Event]]:
        with self._lock:
            return [copy.copy(s) for s in self.stages.values()], list(self.events)

    def duration(self, stage: str) -> float | None:
        with self._lock:
            s = self.stages[stage]
            if s.started is None:
                return None
            return (s.ended if s.ended is not None else self._now()) - s.started

    def done_count(self) -> tuple[int, int]:
        with self._lock:
            done = sum(s.status in (Status.COMPLETED, Status.FAILED, Status.SKIPPED) for s in self.stages.values())
            return done, len(self.stages)

    def current_label(self) -> str:
        with self._lock:
            running = [s.label for s in self.stages.values() if s.status is Status.RUNNING]
        return " + ".join(running)

    def retries(self) -> int:
        with self._lock:
            return sum(max(0, st.attempts - 1) for st in self.stages.values())

    def summary(self) -> dict:
        """Compact, credential-free record for the Pipeline Monitor history."""
        stages, _ = self.view()
        errs = [st for st in stages if st.error]
        return {
            "run_id": self.run_id, "kind": self.kind, "label": self.query[:60], "status": self.overall,
            "duration_s": round(self.elapsed(), 2), "model": self.model_id, "retries": self.retries(),
            "error_category": errs[0].error.category.value if errs else "",
            "stages": [{"id": st.id, "label": st.label, "status": st.status.value,
                        "duration_s": round(self.duration(st.id) or 0, 2), "attempts": st.attempts,
                        "cached": st.cached, "note": (st.note or "")[:160]} for st in stages],
        }

    def errors(self) -> list[Stage]:
        with self._lock:
            return [copy.copy(s) for s in self.stages.values() if s.status is Status.FAILED]

    @property
    def overall(self) -> str:
        """running | completed | partial | failed"""
        with self._lock:
            failed = {s.id for s in self.stages.values() if s.status is Status.FAILED}
            running = any(s.status is Status.RUNNING for s in self.stages.values())
            if failed & self._critical and self.stages[self._primary].status is not Status.COMPLETED:
                return "failed"
            if failed:
                return "partial"
            if running or self._finished is None:
                return "running"
            return "completed"


# --------------------------------------------------------------------------- helpers
@contextmanager
def stage_scope(run: PipelineRun, stage: str) -> Iterator[None]:
    """Mark a stage running; on any exception record it as failed and raise AppError."""
    run.start(stage)
    try:
        yield
    except AppError as err:
        if run.stage(stage).status is not Status.FAILED:
            run.fail(stage, err)
        raise
    except Exception as exc:  # unexpected bugs are classified, logged and surfaced, never swallowed
        err = classify(exc, stage=stage)
        run.fail(stage, err)
        raise err from exc


def backoff_delay(attempt: int, retry_after: float | None = None) -> float:
    delay = min(BASE_DELAY_S * (2 ** (attempt - 1)), MAX_DELAY_S)
    if retry_after:
        delay = min(max(delay, retry_after), MAX_DELAY_S)
    return delay * (1 + random.random() * 0.25)


def call_with_retries(
    fn: Callable[[], T],
    *,
    run: PipelineRun | None = None,
    stage: str = "",
    source: str = "",
    secrets: Iterable[str] = (),
    provider_label: str = "",
    max_attempts: int = MAX_ATTEMPTS,
) -> T:
    """Run `fn`, retrying only transient failures with exponential backoff.

    Permanent errors (bad credentials, unknown model, invalid input) are raised at once.
    Malformed model output is retried at most once. Always raises a classified AppError.
    """
    secrets = list(secrets)
    attempt = 1
    while True:
        try:
            return fn()
        except Exception as exc:
            err = classify(exc, stage=stage, source=source, secrets=secrets, provider_label=provider_label)
            cap = 2 if err.category is ErrorCategory.MALFORMED else max_attempts
            if not err.retryable or attempt >= cap:
                if err is not exc:
                    raise err from None
                raise
            delay = backoff_delay(attempt, err.retry_after)
            if run is not None:
                run.retrying(stage, attempt, err, delay)
            else:
                logger.warning("stage=%s attempt %d failed [%s]; retrying in %.1fs", stage, attempt, err.category.value, delay)
            _sleep(delay)
            attempt += 1


# --------------------------------------------------------------------------- diagnostics
def diagnostics_text(run: PipelineRun) -> str:
    """Sanitised plain-text report that is safe to paste into a bug report."""
    stages, events = run.view()
    lines = [
        "CineCritic diagnostics",
        f"run_id:   {run.run_id} ({run.kind})",
        f"started:  {run.started_at.isoformat(timespec='seconds')}",
        f"query:    {run.query[:120]}",
        f"model:    {run.model_id or '-'}",
        f"overall:  {run.overall}   elapsed: {run.elapsed():.1f}s",
        "",
        "stages:",
    ]
    for s in stages:
        dur = run.duration(s.id)
        err = f" [{s.error.category.value}] {s.error.technical[:160]}" if s.error else ""
        lines.append(
            f"  {s.id:<10} {s.status.value:<10} {(f'{dur:.1f}s' if dur is not None else '-'):>6}  "
            f"attempts={s.attempts}{' cached' if s.cached else ''}{err}"
        )
    lines += ["", "events:"]
    lines += [f"  +{e.t:6.2f}s {e.stage:<10} {e.level.upper():<5} {e.message}" for e in events]
    return redact("\n".join(lines))
