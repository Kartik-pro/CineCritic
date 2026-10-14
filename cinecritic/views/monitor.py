"""System & AI › Pipeline Monitor, API Usage Monitor and Diagnostics."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import platform
import sys
import time
from collections import defaultdict

import streamlit as st

from .. import metadata
from ..ai.providers import package_available
from ..config import APP_VERSION, PROVIDERS
from ..errors import redact
from ..features import monitoring
from ..pipeline import KIND_LABELS, diagnostics_text
from ..ui.common import header
from ..ui.components import compact, fmt_dur, pipeline_html
from ..ui.runtime import get_ctx
from ..ui.state import workspace


def _ts(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- pipeline monitor
def render_pipeline() -> None:
    ws = workspace()
    header("Pipeline Monitor", "Every analysis, discovery, chat and battle run in this session, stage by stage.")
    runs = ws.recent_runs()
    last = st.session_state.get("last_run")
    if last is not None:
        with st.expander("Latest run", expanded=True):
            st.markdown(compact(pipeline_html(last)), unsafe_allow_html=True)
    if not runs:
        st.info("No runs yet. Analyse a film or ask the critic, and the run appears here.")
        return
    total = len(runs)
    bad = sum(r["status"] == "failed" for r in runs)
    partial = sum(r["status"] == "partial" for r in runs)
    durs = [r["duration_s"] for r in runs if r["status"] in ("completed", "partial")]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Runs", total)
    m2.metric("Failed", bad)
    m3.metric("Partial", partial)
    m4.metric("Avg duration", fmt_dur(sum(durs) / len(durs)) if durs else "—")
    c1, c2 = st.columns(2)
    kind = c1.selectbox("Type", ["", *KIND_LABELS], format_func=lambda k: KIND_LABELS.get(k, "All"), key="pm_kind")
    status = c2.selectbox("Outcome", ["", "completed", "partial", "failed"], format_func=lambda s: s or "All", key="pm_st")
    rows = [r for r in runs if (not kind or r["kind"] == kind) and (not status or r["status"] == status)]
    st.dataframe([{"When": _ts(r["ts"]), "Type": KIND_LABELS.get(r["kind"], r["kind"]), "Subject": r["label"],
                   "Outcome": r["status"], "Duration": fmt_dur(r["duration_s"]), "Retries": r["retries"],
                   "Model": r["model"], "Error": r["error_category"], "Run": r["run_id"]} for r in rows],
                 hide_index=True, use_container_width=True)
    if rows:
        pick = st.selectbox("Inspect a run", [r["run_id"] for r in rows], key="pm_pick",
                            format_func=lambda i: next(f"{_ts(r['ts'])} · {r['label']} ({r['status']})" for r in rows if r["run_id"] == i))
        run = next(r for r in rows if r["run_id"] == pick)
        st.dataframe([{"Stage": s["label"], "Status": s["status"], "Duration": fmt_dur(s["duration_s"]),
                       "Attempts": s["attempts"], "Cached": "yes" if s["cached"] else "", "Note": s["note"]}
                      for s in run["stages"]], hide_index=True, use_container_width=True)
        events = [e for e in ws.usage_events() if e["run_id"] == pick]
        if events:
            st.markdown("**Model request lifecycle**")
            for e in events:
                marks = " → ".join(f"{m['stage']} {m['t']:.2f}s" + ("" if m["ok"] else " ✕") for m in e["stages"])
                st.caption(f"{e['provider']}:{e['model']} · {e['task']} · {'ok' if e['ok'] else e['error_category']}"
                           f"{' · fallback' if e['fallback'] else ''} · {marks}")
    agg = defaultdict(list)
    for r in runs:
        for s in r["stages"]:
            if s["status"] == "completed" and not s["cached"]:
                agg[s["label"]].append(s["duration_s"])
    if agg:
        st.markdown("**Average stage duration (seconds)**")
        st.bar_chart({k: sum(v) / len(v) for k, v in agg.items()}, horizontal=True)
    st.download_button("Download run history (JSON)", json.dumps(runs, indent=2, default=str),
                       "cinecritic-runs.json", "application/json", icon=":material/data_object:")


# --------------------------------------------------------------------------- usage monitor
PERIODS = {"Last 24 hours": 86400, "Last 7 days": 7 * 86400, "Last 30 days": 30 * 86400, "This session": None}


def render_usage() -> None:
    ctx = get_ctx()
    ws = ctx.ws
    header("API Usage Monitor", "Requests this app sent to AI providers in this session. Provider dashboards remain "
                                "the source of truth for billing and remaining quota.")
    events = ws.usage_events()
    if not events:
        st.info("No AI requests yet. Usage appears here after your first analysis, chat or comparison.")
        return
    c1, c2, c3 = st.columns(3)
    period = c1.selectbox("Period", list(PERIODS), index=3, key="um_period")
    provider = c2.selectbox("Provider", ["", *PROVIDERS], format_func=lambda x: x or "All", key="um_prov")
    models = sorted({e["model"] for e in events if not provider or e["provider"] == provider})
    model = c3.selectbox("Model", ["", *models], format_func=lambda x: x or "All", key="um_model")
    since = time.time() - PERIODS[period] if PERIODS[period] else None
    shown = monitoring.filter_events(events, since=since, provider=provider or None, model=model or None)
    pricing = ctx.prefs["pricing"]
    if not shown:
        st.info("No requests match these filters.")
        return
    s = monitoring.summarize(shown, pricing)
    for lim in monitoring.limit_statuses(events, ctx.prefs):
        (st.error if lim.level == "over" else st.warning if lim.level == "warn" else st.info)(
            f"{lim.name}: {lim.used:,.2f} of {lim.limit:,.2f} {lim.unit} ({lim.pct:.0f}%)")
        st.progress(min(1.0, lim.pct / 100))
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Requests", s["total"])
    m2.metric("Success rate", f"{100 * s['ok'] / s['total']:.0f}%")
    m3.metric("Failed", s["failed"])
    m4.metric("Retries", s["retries"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tokens in / out", f"{s['input_tokens']:,} / {s['output_tokens']:,}" if s["calls_with_tokens"] else "not reported")
    m2.metric("Latency avg / p95", f"{s['latency_avg_ms']} / {s['latency_p95_ms']} ms" if s["latency_avg_ms"] is not None else "—")
    m3.metric("Fallbacks used", s["fallbacks"])
    m4.metric("Est. cost", f"${s['cost_usd']:.4f}" if s["cost_usd"] is not None else "no prices set")
    if s["calls_without_tokens"]:
        st.caption(f"{s['calls_without_tokens']} request(s) did not report token counts, so totals may be understated.")
    if s["unpriced_calls"] and s["priced_calls"]:
        st.caption(f"Cost covers {s['priced_calls']} priced request(s); {s['unpriced_calls']} had no price or tokens.")
    st.caption(f"Rate-limit errors: {s['rate_limit_events']} (of which quota-related: {s['quota_events']}) · "
               f"timeouts: {s['timeouts']}. Remaining provider quota is not available to this app.")
    st.caption("Sources — requests, failures, retries, latency: measured locally by CineCritic. Tokens: provider-reported, "
               "when the provider returns them. Cost: estimated from prices you entered. Provider quota/billing: unavailable.")
    st.markdown("#### By model")
    st.dataframe([{"Provider": r["provider"], "Model": r["model"], "Requests": r["requests"], "Failed": r["failed"],
                   "Tokens in": r["input_tokens"] if r["tokens_known"] else None,
                   "Tokens out": r["output_tokens"] if r["tokens_known"] else None,
                   "Avg latency (ms)": r["avg_latency_ms"],
                   "Est. cost": round(r["cost"], 5) if r["cost"] is not None else None} for r in s["by_model"]],
                 hide_index=True, use_container_width=True)
    if len(s["daily"]) > 1:
        st.markdown("#### Requests per day")
        st.bar_chart({d: v["requests"] for d, v in s["daily"].items()})
    st.markdown("#### Monthly totals")
    st.dataframe([{"Month": m, "Requests": v["requests"], "Failed": v["failed"], "Tokens": v["tokens"],
                   "Est. cost": round(v["cost"], 4)} for m, v in s["monthly"].items()], hide_index=True,
                 use_container_width=True)
    st.markdown("#### Recent requests")
    st.caption("Prompts and responses are never recorded.")
    st.dataframe([{"When": _ts(e["ts"]), "Provider": e["provider"], "Model": e["model"], "Task": e["task"],
                   "OK": "yes" if e["ok"] else "no", "Latency (ms)": e["latency_ms"], "In": e["in_tokens"],
                   "Out": e["out_tokens"], "Retries": e["retries"], "Error": e["error_category"],
                   "Fallback": "yes" if e["fallback"] else ""} for e in shown[:200]],
                 hide_index=True, use_container_width=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "provider", "model", "task", "ok", "latency_ms", "in_tokens", "out_tokens", "retries",
                "error_category", "fallback"])
    for e in shown:
        w.writerow([_ts(e["ts"]), e["provider"], e["model"], e["task"], int(e["ok"]), e["latency_ms"], e["in_tokens"],
                    e["out_tokens"], e["retries"], e["error_category"], int(e["fallback"])])
    st.download_button("Download usage (CSV)", buf.getvalue(), "cinecritic-usage.csv", "text/csv",
                       icon=":material/table:")


# --------------------------------------------------------------------------- diagnostics
def _self_tests() -> list[tuple[str, bool, str]]:
    """Real checks of application logic that need no network and no keys."""
    from .. import errors, spoilers
    from ..schemas import Critique
    from ..storage.workspace import Workspace
    out = []
    try:
        w = Workspace()
        w.upsert_archive("t:x", "X", status="watched", rating=8.0)
        w2 = Workspace()
        w2.import_data(w.export_json())
        out.append(("Backup round-trip", w2.get_archive_entry("t:x") is not None, "export → import preserves the archive"))
    except Exception as exc:
        out.append(("Backup round-trip", False, type(exc).__name__))
    secret = "sk-test-0123456789abcdef0123456789"
    out.append(("Secret redaction", secret not in errors.redact(f"failed with key {secret}", [secret]),
                "keys are removed from error text"))
    text, removed = spoilers.clean_text("It starts well. In the end, the hero dies.", "none")
    out.append(("Spoiler filter", removed >= 1 and "dies" not in text, "outcome sentences are removed at spoiler-free level"))
    return out


def render_diagnostics() -> None:
    ctx = get_ctx()
    ws = ctx.ws
    header("Diagnostics", "Health checks built from this session's real state. Nothing here contains keys.")
    events = ws.usage_events()
    provider_state = {}
    for label, p in PROVIDERS.items():
        rec = ctx.statuses.get(label)
        provider_state[label] = {"configured": bool(ctx.keys[label]), "package": package_available(p),
                                 "state": rec.state if rec else "unknown",
                                 "detail": (rec.message if rec else "Key present; connection not tested yet.")[:160]}
    problems = []
    if not any(ctx.keys.values()):
        problems.append("No AI provider key is configured, so analyses cannot run.")
    checks = monitoring.health_checks(
        workspace_counts=ws.counts(), provider_state=provider_state, tmdb_configured=bool(ctx.tmdb_key),
        cache=metadata.cache_stats(), breaker=ctx.gateway.breaker.snapshot(),
        recent_errors=sum(not e["ok"] for e in events), config_problems=problems)
    icon = {"ok": "✅", "warn": "⚠️", "fail": "❌"}
    for c in checks:
        st.markdown(f"{icon[c.level]} **{c.name}** — {c.detail}")
    st.markdown("#### Self-tests")
    if st.button("Run self-tests", key="dg_selftest", icon=":material/rule:"):
        for name, ok, what in _self_tests():
            (st.success if ok else st.error)(f"{name}: {'pass' if ok else 'FAIL'} — {what}")
    st.markdown("#### Environment")
    try:
        import streamlit
        sv = streamlit.__version__
    except Exception:
        sv = "unknown"
    env = {"CineCritic": APP_VERSION, "Python": platform.python_version(), "Streamlit": sv,
           "Platform": platform.system(), "LangChain providers installed": ", ".join(
               l for l, p in PROVIDERS.items() if package_available(p)) or "none"}
    st.table(env)
    st.markdown("#### Caches")
    cs = metadata.cache_stats()
    st.write(f"Metadata: {cs['details_entries']} entries ({cs['details_hits']} hits / {cs['details_misses']} misses) · "
             f"listings: {cs['listing_entries']} entries ({cs['listing_hits']} hits / {cs['listing_misses']} misses)")
    c1, c2 = st.columns(2)
    if c1.button("Clear TMDB caches", key="dg_clear_tmdb"):
        metadata.clear_cache()
        st.toast("TMDB caches cleared.")
    if c2.button("Clear analysis caches", key="dg_clear_an"):
        from ..services import CRITIQUE_CACHE, RECOS_CACHE
        CRITIQUE_CACHE.clear(), RECOS_CACHE.clear()
        st.toast("Analysis caches cleared.")
    st.markdown("#### Report")
    last = st.session_state.get("last_run")
    report = "\n".join([
        f"CineCritic {APP_VERSION} · Python {platform.python_version()} · {_ts(time.time())}",
        *(f"[{c.level}] {c.name}: {c.detail}" for c in checks), "",
        diagnostics_text(last) if last is not None else "No run recorded yet."])
    secrets = ctx.secrets
    st.code(redact(report, secrets), language="text")
