"""AI gateway: the single place where application-managed model requests are routed.

Responsibilities
* resolve the task profile (primary model, optional fallback, generation settings);
* refuse early (no key, key known invalid, budget reached, provider temporarily suppressed);
* run the call with bounded retries + exponential backoff (pipeline.call_with_retries);
* fall back to the configured fallback model ONLY when one is configured, and say so in the
  pipeline events and in `produced` (never a silent model switch);
* record one usage event per attempt chain (tokens when reported, latency, retries, error
  category, lifecycle timestamps) without storing prompts, payloads or credentials.

Request lifecycle recorded per attempt chain:
accepted -> validated -> selected -> dispatched -> response received -> output validated -> returned
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, TypeVar

from ..config import PROVIDERS, TASKS
from ..errors import AppError, ErrorCategory, MissingAPIKeyError, classify
from ..pipeline import PipelineRun, call_with_retries
from ..prefs import Profile
from .providers import ModelRef, build_llm
from .usage import UsageCollector

T = TypeVar("T")

LIFECYCLE = ("accepted", "validated", "selected", "dispatched", "response received", "output validated", "returned")
_FALLBACK_OK = {ErrorCategory.RATE_LIMIT, ErrorCategory.TIMEOUT, ErrorCategory.NETWORK, ErrorCategory.PROVIDER,
                ErrorCategory.MODEL, ErrorCategory.AUTH, ErrorCategory.MALFORMED}
_TRANSIENT = {ErrorCategory.RATE_LIMIT, ErrorCategory.TIMEOUT, ErrorCategory.NETWORK, ErrorCategory.PROVIDER}


class CircuitBreaker:
    """Temporarily suppress a provider after repeated transient failures."""

    def __init__(self, threshold: int = 3, window_s: float = 120, cooldown_s: float = 60,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.threshold, self.window_s, self.cooldown_s, self._clock = threshold, window_s, cooldown_s, clock
        self._fails: dict[str, list[float]] = {}
        self._open_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def allow(self, provider: str) -> bool:
        with self._lock:
            return self._clock() >= self._open_until.get(provider, 0.0)

    def remaining(self, provider: str) -> float:
        with self._lock:
            return max(0.0, self._open_until.get(provider, 0.0) - self._clock())

    def success(self, provider: str) -> None:
        with self._lock:
            self._fails.pop(provider, None)
            self._open_until.pop(provider, None)

    def failure(self, provider: str, err: AppError) -> None:
        if err.category not in _TRANSIENT:
            return          # bad keys / unknown models are configuration problems, not outages
        with self._lock:
            now = self._clock()
            recent = [t for t in self._fails.get(provider, []) if now - t <= self.window_s] + [now]
            self._fails[provider] = recent
            if len(recent) >= self.threshold:
                self._open_until[provider] = now + self.cooldown_s

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            now = self._clock()
            return {p: round(t - now, 1) for p, t in self._open_until.items() if t > now}


@dataclass
class _Lifecycle:
    clock: Callable[[], float]
    t0: float = 0.0
    marks: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.t0 = self.clock()

    def mark(self, name: str, ok: bool = True) -> None:
        self.marks.append({"stage": name, "t": round(self.clock() - self.t0, 3), "ok": ok})


class Gateway:
    def __init__(
        self,
        *,
        profile_for: Callable[[str], Profile],
        key_for: Callable[[str], str],
        record: Callable[..., None] | None = None,
        builder: Callable[..., object] = build_llm,
        preflight: Callable[[ModelRef, str], AppError | None] | None = None,
        over_budget: Callable[[], bool] = lambda: False,
        breaker: CircuitBreaker | None = None,
        max_attempts: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._profile_for, self._key_for, self._record = profile_for, key_for, record
        self._builder, self._preflight, self._over_budget = builder, preflight, over_budget
        self.breaker = breaker or CircuitBreaker()
        self.max_attempts, self._clock = max_attempts, clock
        self._lock = threading.Lock()
        self.produced: dict[str, ModelRef] = {}
        self.fallback_used: dict[str, str] = {}

    # ------------------------------------------------------------------ planning
    def plan(self, task: str) -> tuple[Profile, list[ModelRef]]:
        if task not in TASKS:
            raise AppError(ErrorCategory.INVALID_INPUT, f"Unknown AI task “{task}”.")
        profile = self._profile_for(task)
        refs = [profile.primary] + ([profile.fallback] if profile.fallback else [])
        return profile, refs

    def label(self, task: str) -> str:
        """Short display text for the model that will be tried first."""
        return str(self.plan(task)[1][0])

    def _usable(self, ref: ModelRef) -> AppError | None:
        key = self._key_for(ref.provider)
        if not key:
            return MissingAPIKeyError(ref.provider)
        if self._preflight:
            err = self._preflight(ref, key)
            if err is not None:
                return err
        if not self.breaker.allow(ref.provider):
            wait = int(self.breaker.remaining(ref.provider)) + 1
            return AppError(ErrorCategory.PROVIDER, f"{ref.provider} is paused for about {wait}s after repeated "
                            "failures. It will be retried automatically.", source="ai", retryable=True)
        return None

    def _build(self, ref: ModelRef, profile: Profile):
        return self._builder(ref, self._key_for(ref.provider), temperature=profile.temperature,
                             max_tokens=profile.max_tokens, timeout=profile.timeout_s)

    def prepare(self, task: str, run: PipelineRun | None = None, stage: str = "init") -> ModelRef:
        """Validate that at least one configured model can be used and constructed. Raises AppError."""
        profile, refs = self.plan(task)
        first_err: AppError | None = None
        for i, ref in enumerate(refs):
            err = self._usable(ref)
            if err is None:
                try:
                    self._build(ref, profile)
                except Exception as exc:  # construction problems (missing package, bad settings)
                    err = classify(exc, stage=stage, source="ai", provider_label=ref.provider,
                                   secrets=[self._key_for(ref.provider)])
            if err is None:
                if i and run is not None:
                    run.event(stage, "warn", f"primary model {refs[0]} unavailable ({first_err.category.value if first_err else '?'}); "
                              f"fallback {ref} will be used")
                return ref
            first_err = first_err or err
        raise first_err  # type: ignore[misc]

    # ------------------------------------------------------------------ execution
    def call(self, task: str, fn: Callable[[object, dict], T], *, run: PipelineRun | None = None, stage: str = "",
             secrets: Iterable[str] = (), validate: Callable[[T], None] | None = None) -> T:
        """Run `fn(llm, config)` under the task's profile with retries and optional fallback."""
        life = _Lifecycle(self._clock)
        life.mark("accepted")
        profile, refs = self.plan(task)
        if self._over_budget():
            life.mark("validated", ok=False)
            raise AppError(ErrorCategory.BUDGET, "Your configured monthly AI budget has been reached, so no new "
                           "requests are sent. Raise or clear the limit in AI Control Center → Preferences.",
                           source="ai", stage=stage)
        life.mark("validated")
        secrets = [s for s in (*secrets, *(self._key_for(r.provider) for r in refs)) if s]
        errors: list[AppError] = []
        for idx, ref in enumerate(refs):
            err = self._usable(ref)
            if err is not None:
                errors.append(err)
                if run is not None:
                    run.event(stage or "ai", "warn", f"{ref} skipped: {err.message[:120]}")
                continue
            life.mark("selected")
            collector, calls, started = UsageCollector(), [0], self._clock()
            try:
                llm = self._build(ref, profile)

                def attempt(llm=llm, collector=collector):
                    calls[0] += 1
                    return fn(llm, {"callbacks": [collector]})

                life.mark("dispatched")
                result = call_with_retries(attempt, run=run, stage=stage, source="ai", secrets=secrets,
                                           provider_label=ref.provider, max_attempts=self.max_attempts)
                life.mark("response received")
                if validate is not None:
                    validate(result)
                life.mark("output validated")
            except Exception as exc:
                app_err = classify(exc, stage=stage, source="ai", provider_label=ref.provider, secrets=secrets)
                life.mark("response received" if calls[0] else "dispatched", ok=False)
                self.breaker.failure(ref.provider, app_err)
                self._log(task, ref, ok=False, started=started, collector=collector, retries=max(0, calls[0] - 1),
                          err=app_err, run=run, fallback=bool(idx), life=life)
                errors.append(app_err)
                if app_err.category not in _FALLBACK_OK or idx == len(refs) - 1:
                    break
                if run is not None:
                    run.event(stage or "ai", "warn", f"{ref} failed [{app_err.category.value}]; "
                              f"trying configured fallback {refs[idx + 1]}")
                continue
            life.mark("returned")
            self.breaker.success(ref.provider)
            self._log(task, ref, ok=True, started=started, collector=collector, retries=max(0, calls[0] - 1),
                      err=None, run=run, fallback=bool(idx), life=life)
            with self._lock:
                self.produced[task] = ref
                if idx:
                    self.fallback_used[task] = f"{refs[0]} → {ref}"
            return result
        raise errors[0] if errors else AppError(ErrorCategory.PROVIDER, "No model could be used.", source="ai")

    def _log(self, task, ref, *, ok, started, collector, retries, err, run, fallback, life) -> None:
        if self._record is None:
            return
        try:
            self._record(provider=ref.provider, model=ref.model, task=task, ok=ok,
                         latency_ms=int((self._clock() - started) * 1000), in_tokens=collector.input_tokens,
                         out_tokens=collector.output_tokens, retries=retries,
                         error_category=err.category.value if err else "",
                         error_message=err.message[:300] if err else "", run_id=run.run_id if run else "",
                         fallback=fallback, stages=life.marks)
        except Exception:  # monitoring must never break a request
            pass

    def model_used(self, task: str) -> str:
        with self._lock:
            ref = self.produced.get(task)
        return str(ref) if ref else ""
