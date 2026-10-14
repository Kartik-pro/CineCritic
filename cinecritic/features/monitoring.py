"""Usage accounting and health checks for the monitoring pages (pure functions, no Streamlit).

Only requests made by THIS session of CineCritic are known; provider-side account usage is not
queried, and the UI says so. Token counts are summed only where the provider reported them;
costs use only prices the user configured. Anything unknown stays unknown.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from ..ai.usage import estimate_cost, price_key


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def _month(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m")


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))]


def _cost(event: dict, pricing: dict) -> float | None:
    return estimate_cost(event.get("in_tokens"), event.get("out_tokens"),
                         pricing.get(price_key(event["provider"], event["model"])))


def filter_events(events: list[dict], *, since: float | None = None, provider: str | None = None,
                  model: str | None = None) -> list[dict]:
    return [e for e in events if (since is None or e["ts"] >= since) and (not provider or e["provider"] == provider)
            and (not model or e["model"] == model)]


def summarize(events: list[dict], pricing: dict | None = None) -> dict[str, Any]:
    pricing = pricing or {}
    ok = [e for e in events if e["ok"]]
    failed = [e for e in events if not e["ok"]]
    latencies = [e["latency_ms"] for e in ok if e.get("latency_ms") is not None]
    with_tokens = [e for e in events if e.get("in_tokens") is not None or e.get("out_tokens") is not None]
    quota_words = ("quota", "exhausted", "billing")
    by_model: dict[tuple[str, str], dict] = {}
    daily: dict[str, dict] = defaultdict(lambda: {"requests": 0, "failed": 0, "tokens": 0})
    monthly: dict[str, dict] = defaultdict(lambda: {"requests": 0, "failed": 0, "tokens": 0, "cost": 0.0})
    total_cost, priced, unpriced = 0.0, 0, 0
    for e in events:
        row = by_model.setdefault((e["provider"], e["model"]), {
            "provider": e["provider"], "model": e["model"], "requests": 0, "failed": 0, "input_tokens": 0,
            "output_tokens": 0, "tokens_known": 0, "latencies": [], "cost": 0.0, "priced": 0})
        row["requests"] += 1
        row["failed"] += not e["ok"]
        if e.get("in_tokens") is not None or e.get("out_tokens") is not None:
            row["input_tokens"] += e.get("in_tokens") or 0
            row["output_tokens"] += e.get("out_tokens") or 0
            row["tokens_known"] += 1
        if e["ok"] and e.get("latency_ms") is not None:
            row["latencies"].append(e["latency_ms"])
        c = _cost(e, pricing)
        if c is None:
            unpriced += 1
        else:
            priced += 1
            row["cost"] += c
            row["priced"] += 1
            total_cost += c
            monthly[_month(e["ts"])]["cost"] += c
        tokens = (e.get("in_tokens") or 0) + (e.get("out_tokens") or 0)
        d, m = daily[_day(e["ts"])], monthly[_month(e["ts"])]
        for bucket in (d, m):
            bucket["requests"] += 1
            bucket["failed"] += not e["ok"]
            bucket["tokens"] += tokens
    models = []
    for row in by_model.values():
        lat = row.pop("latencies")
        row["avg_latency_ms"] = round(mean(lat)) if lat else None
        row["cost"] = row["cost"] if row["priced"] else None
        models.append(row)
    models.sort(key=lambda r: -r["requests"])
    return {
        "total": len(events), "ok": len(ok), "failed": len(failed), "fallbacks": sum(bool(e.get("fallback")) for e in events),
        "input_tokens": sum(e.get("in_tokens") or 0 for e in events),
        "output_tokens": sum(e.get("out_tokens") or 0 for e in events),
        "calls_with_tokens": len(with_tokens), "calls_without_tokens": len(events) - len(with_tokens),
        "rate_limit_events": sum(e["error_category"] == "rate_limit" for e in failed),
        "quota_events": sum(e["error_category"] == "rate_limit" and any(w in e["error_message"].lower() for w in quota_words)
                            for e in failed),
        "timeouts": sum(e["error_category"] == "timeout" for e in failed),
        "retries": sum(e.get("retries") or 0 for e in events),
        "latency_avg_ms": round(mean(latencies)) if latencies else None,
        "latency_p50_ms": _pct(latencies, 0.5), "latency_p95_ms": _pct(latencies, 0.95),
        "cost_usd": total_cost if priced else None, "priced_calls": priced, "unpriced_calls": unpriced,
        "by_model": models, "daily": dict(sorted(daily.items())), "monthly": dict(sorted(monthly.items())),
    }


@dataclass(frozen=True)
class LimitStatus:
    name: str
    used: float
    limit: float
    pct: float
    level: str        # ok | warn | over
    unit: str = ""

    @property
    def alert_key(self) -> str:
        return f"{self.name}:{self.level}"


def limit_statuses(events: list[dict], prefs: dict, pricing: dict | None = None, now: float | None = None
                   ) -> list[LimitStatus]:
    """Progress against limits the user configured. Unconfigured limits are simply not listed."""
    now = now or time.time()
    pricing = pricing or prefs.get("pricing") or {}
    threshold = float(prefs.get("alert_threshold_pct", 80))
    out: list[LimitStatus] = []

    def add(name: str, used: float, limit: float, unit: str) -> None:
        pct = used / limit * 100 if limit else 0.0
        level = "over" if pct >= 100 else "warn" if pct >= threshold else "ok"
        out.append(LimitStatus(name, used, limit, min(pct, 999.0), level, unit))

    if prefs.get("daily_request_limit"):
        today = _day(now)
        add("Requests today", sum(_day(e["ts"]) == today for e in events), prefs["daily_request_limit"], "requests")
    if prefs.get("monthly_budget_usd"):
        month = _month(now)
        spent = sum(c for e in events if _month(e["ts"]) == month and (c := _cost(e, pricing)) is not None)
        add("Estimated spend this month", spent, prefs["monthly_budget_usd"], "USD")
    return out


def over_budget(events: list[dict], prefs: dict, now: float | None = None) -> bool:
    """True when a hard budget stop is enabled and the estimated monthly spend reached the budget."""
    if not (prefs.get("hard_budget_stop") and prefs.get("monthly_budget_usd")):
        return False
    return any(s.name.startswith("Estimated") and s.level == "over" for s in limit_statuses(events, prefs, now=now))


# --------------------------------------------------------------------------- diagnostics
@dataclass(frozen=True)
class Check:
    name: str
    level: str        # ok | warn | fail
    detail: str


def health_checks(*, workspace_counts: dict[str, int] | None, provider_state: dict[str, dict], tmdb_configured: bool,
                  cache: dict[str, int], breaker: dict[str, float], recent_errors: int,
                  config_problems: list[str]) -> list[Check]:
    """Assemble real application checks (callers pass in measured facts)."""
    checks = [Check("Workspace", "ok" if workspace_counts is not None else "fail",
                    "In-session storage reachable; "
                    + (", ".join(f"{k} {v}" for k, v in workspace_counts.items()) if workspace_counts is not None
                       else "unavailable") + ". No database is used; data resets when the session ends unless "
                    "you download a backup.")]
    for label, info in provider_state.items():
        if not info["configured"]:
            checks.append(Check(f"Provider: {label}", "warn", "No API key configured."))
        elif not info["package"]:
            checks.append(Check(f"Provider: {label}", "fail", "Key present but the LangChain package is not installed."))
        else:
            checks.append(Check(f"Provider: {label}", {"valid": "ok", "invalid": "fail", "failed": "warn"}.get(
                info["state"], "warn"), info["detail"]))
    checks.append(Check("TMDB", "ok" if tmdb_configured else "warn",
                        "Key configured." if tmdb_configured else "No TMDB key: discovery, search, posters and "
                                                                  "verified credits are unavailable."))
    total = cache.get("details_hits", 0) + cache.get("details_misses", 0)
    ratio = f"{cache.get('details_hits', 0)}/{total} metadata lookups served from cache" if total else "no lookups yet"
    checks.append(Check("Cache", "ok", f"{cache.get('details_entries', 0)} detail and {cache.get('listing_entries', 0)} "
                                       f"listing entries; {ratio}."))
    if breaker:
        checks.append(Check("Circuit breaker", "warn", "Temporarily paused: " + ", ".join(
            f"{p} ({int(s)}s)" for p, s in breaker.items())))
    else:
        checks.append(Check("Circuit breaker", "ok", "No provider is suppressed."))
    checks.append(Check("Recent errors", "ok" if recent_errors == 0 else "warn",
                        f"{recent_errors} failed AI request(s) recorded in this session."))
    for problem in config_problems:
        checks.append(Check("Configuration", "warn", problem))
    return checks
