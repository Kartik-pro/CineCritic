"""System & AI › AI Control Center (overview, providers, models, task profiles, comparison, keys, preferences)."""
from __future__ import annotations

import datetime as dt

import streamlit as st

from .. import credentials, prefs as P, spoilers
from ..ai.providers import ModelRef, discover_models, package_available
from ..config import (DIMENSIONS, LANGUAGES, MAX_WEIGHT, PROVIDERS, SAFE_MAX_TOKENS_RANGE, SAFE_TIMEOUT_RANGE,
                      SCORE_SCALES, TASKS)
from ..features import compare_models as cmp, monitoring
from ..ui.common import header, show_error
from ..ui.runtime import Ctx, get_ctx, save_prefs
from ..ui.state import workspace


# --------------------------------------------------------------------------- helpers
def _default_model(ctx: Ctx, provider: str) -> str:
    p = ctx.prefs
    return (p["default_model"] if p["default_provider"] == provider and p["default_model"]
            else PROVIDERS[provider].default_model)


def _status(ctx: Ctx, service: str) -> tuple[str, str]:
    if service == "TMDB":
        return credentials.status_label("TMDB", "", ctx.tmdb_key, ctx.statuses.get("TMDB"))
    model = _default_model(ctx, service)
    return credentials.status_label(service, model, ctx.keys[service], ctx.statuses.get(service))


def _test(ctx: Ctx, service: str, model: str = "") -> None:
    ss = st.session_state
    with st.spinner(f"Testing {service}…"):
        if service == "TMDB":
            rec = credentials.check_tmdb(ctx.tmdb_key)
        else:
            rec = credentials.check_ai(PROVIDERS[service], model or _default_model(ctx, service), ctx.keys[service])
    ss.key_status[service] = rec
    (st.success if rec.state == "valid" else st.error if rec.state == "invalid" else st.warning)(
        rec.message + (f" ({rec.category})" if rec.category else ""))


def _model_options(provider: str) -> list[str]:
    found = st.session_state.models_found.get(provider)
    ids = [m.id for m in found.models if m.chat is not False] if found and found.ok else []
    return ids


def _model_picker(label: str, provider: str, current: str, key: str, fallback_default: str = "") -> str:
    """Selectbox of discovered models with a manual-entry escape hatch (discovery may be unavailable)."""
    ids = _model_options(provider)
    manual = "✎ Enter manually…"
    options = ([current] if current and current not in ids else []) + ids + [manual]
    if not ids:
        return st.text_input(label, value=current or fallback_default, key=key, max_chars=120,
                             help="Run model discovery on the Models tab to pick from the provider's list.")
    idx = options.index(current) if current in options else 0
    choice = st.selectbox(label, options, index=idx, key=key)
    if choice == manual:
        return st.text_input(f"{label} (manual)", value=current, key=f"{key}_m", max_chars=120)
    return choice


# --------------------------------------------------------------------------- tabs
def _overview(ctx: Ctx) -> None:
    ws = ctx.ws
    rows = []
    for svc in (*PROVIDERS, "TMDB"):
        label, _ = _status(ctx, svc)
        src = ctx.key_source.get(svc, "") if svc != "TMDB" else ctx.tmdb_source
        rows.append({"Service": svc, "Key": f"configured ({src})" if src else "not configured", "Status": label,
                     "Package": "—" if svc == "TMDB" else ("installed" if package_available(PROVIDERS[svc]) else "missing")})
    st.dataframe(rows, hide_index=True, use_container_width=True)
    st.markdown("#### Active task profiles")
    trows = []
    for tid, task in TASKS.items():
        prof = P.resolve_profile(ctx.prefs, tid)
        trows.append({"Task": task.label, "Primary": str(prof.primary),
                      "Fallback": str(prof.fallback) if prof.fallback else "none",
                      "Key ready": "yes" if ctx.keys.get(prof.primary.provider) else "no"})
    st.dataframe(trows, hide_index=True, use_container_width=True)
    for s in monitoring.limit_statuses(ws.usage_events(), ctx.prefs):
        (st.error if s.level == "over" else st.warning if s.level == "warn" else st.info)(
            f"{s.name}: {s.used:,.2f} of {s.limit:,.2f} {s.unit} ({s.pct:.0f}%)")
    st.info("**Storage:** There is no database. Preferences, archive, analyses and usage live in this browser session "
            "and disappear when it ends. Use *Download backup* in the sidebar to keep them. API keys are never "
            "included in backups.", icon=":material/info:")
    st.caption(f"Spoiler protection default: **{spoilers.LABELS[ctx.prefs['spoiler_level']]}** · "
               f"Score scale 0–{ctx.prefs['score_scale']} · Language {ctx.prefs['language']}")


def _providers(ctx: Ctx) -> None:
    for svc, p in PROVIDERS.items():
        with st.container(border=True):
            label, css = _status(ctx, svc)
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"**{p.label}** · {label}")
            c1.caption(f"Env/secret name `{p.env_var}` · key source: {ctx.key_source.get(svc) or 'none'} · "
                       f"package `{p.pip_name}` {'installed' if package_available(p) else 'NOT installed'} · "
                       f"[get a key]({p.docs_url})")
            rec = ctx.statuses.get(svc)
            if rec and rec.checked_at:
                c1.caption(f"Last test: {rec.state} — {rec.message[:140]}" +
                           (f" · {rec.latency_ms} ms" if rec.latency_ms else "") +
                           (" · rate-limited" if rec.rate_limited else ""))
            if c2.button("Test", key=f"prov_test_{svc}", disabled=not ctx.keys[svc], use_container_width=True):
                _test(ctx, svc)
    with st.container(border=True):
        label, _ = _status(ctx, "TMDB")
        st.markdown(f"**TMDB** · {label}")
        st.caption("Film data and imagery. This product uses the TMDB API but is not endorsed or certified by TMDB.")
        if st.button("Test", key="prov_test_tmdb", disabled=not ctx.tmdb_key):
            _test(ctx, "TMDB")


def _models(ctx: Ctx) -> None:
    st.write("Ask a provider which models your key can use. Lists come straight from the provider; "
             "capabilities are shown only when the provider reports them.")
    c1, c2 = st.columns([2, 1])
    provider = c1.selectbox("Provider", list(PROVIDERS), key="mdl_prov")
    if c2.button("Discover models", key="mdl_go", disabled=not ctx.keys[provider], use_container_width=True,
                 type="primary"):
        with st.spinner("Asking the provider…"):
            st.session_state.models_found[provider] = discover_models(provider, ctx.keys[provider])
    res = st.session_state.models_found.get(provider)
    if res is None:
        st.info("No list yet. You can still type any model ID manually in Task Profiles.")
    elif not res.ok:
        st.warning(res.error + " Enter a model ID manually instead.")
    else:
        when = dt.datetime.fromtimestamp(res.fetched_at).strftime("%H:%M:%S")
        st.caption(f"{len(res.models)} models · fetched {when}")
        q = st.text_input("Filter", key="mdl_q")
        rows = [{"Model ID": m.id, "Name": m.display, "Context (in)": m.input_limit, "Max output": m.output_limit,
                 "Chat": {True: "yes", False: "no", None: "unknown"}[m.chat],
                 "Vision": {True: "yes", False: "no", None: "unknown"}[m.vision]}
                for m in res.models if q.lower() in m.id.lower()]
        st.dataframe(rows, hide_index=True, use_container_width=True)
        if res.models and res.models[0].source:
            st.caption(res.models[0].source)
    st.markdown("#### Default model")
    c1, c2 = st.columns(2)
    dp = c1.selectbox("Default provider", list(PROVIDERS), index=list(PROVIDERS).index(ctx.prefs["default_provider"]),
                      key="mdl_dp")
    with c2:
        dm = _model_picker("Default model", dp, ctx.prefs["default_model"] if dp == ctx.prefs["default_provider"] else "",
                           "mdl_dm", PROVIDERS[dp].default_model)
    if st.button("Save default model", key="mdl_save"):
        save_prefs(default_provider=dp, default_model=dm)
        st.toast("Saved.")
        st.rerun()
    st.caption("Tasks without their own profile use this. Preset model IDs are starting points, not guarantees.")


def _profiles(ctx: Ctx) -> None:
    st.write("Route each AI task to a model. An optional fallback is used only when the primary fails, "
             "and the app always tells you when it was used.")
    current = ctx.prefs["profiles"]
    new: dict = {}
    for tid, task in TASKS.items():
        raw = current.get(tid) or P.PROFILE_DEFAULTS
        eff = P.resolve_profile(ctx.prefs, tid)
        with st.expander(f"{task.label} — now: {eff.primary}" + (f" → fallback {eff.fallback}" if eff.fallback else "")):
            st.caption(task.help)
            use_custom = st.checkbox("Use a custom model for this task", value=bool(raw.get("provider")),
                                     key=f"tp_c_{tid}")
            prof = dict(P.PROFILE_DEFAULTS)
            if use_custom:
                c1, c2 = st.columns(2)
                prov = c1.selectbox("Provider", list(PROVIDERS), key=f"tp_p_{tid}",
                                    index=list(PROVIDERS).index(raw["provider"]) if raw.get("provider") else 0)
                with c2:
                    model = _model_picker("Model", prov, raw.get("model", "") if raw.get("provider") == prov else "",
                                          f"tp_m_{tid}", PROVIDERS[prov].default_model)
                prof.update(provider=prov, model=model)
            use_fb = st.checkbox("Configure a fallback model", value=bool(raw.get("fallback_provider")),
                                 key=f"tp_fc_{tid}")
            if use_fb:
                c1, c2 = st.columns(2)
                fprov = c1.selectbox("Fallback provider", list(PROVIDERS), key=f"tp_fp_{tid}",
                                     index=list(PROVIDERS).index(raw["fallback_provider"]) if raw.get("fallback_provider") else 0)
                with c2:
                    fmodel = _model_picker("Fallback model", fprov,
                                           raw.get("fallback_model", "") if raw.get("fallback_provider") == fprov else "",
                                           f"tp_fm_{tid}", PROVIDERS[fprov].default_model)
                prof.update(fallback_provider=fprov, fallback_model=fmodel)
            c1, c2, c3 = st.columns(3)
            temp_on = c1.checkbox("Set temperature", value=raw.get("temperature") is not None, key=f"tp_to_{tid}")
            temp = c1.slider("Temperature", 0.0, 1.0, float(raw.get("temperature") or 0.3), 0.05, key=f"tp_t_{tid}",
                             disabled=not temp_on)
            mt_on = c2.checkbox("Limit output tokens", value=bool(raw.get("max_tokens")), key=f"tp_mo_{tid}")
            mt = c2.number_input("Max tokens", *SAFE_MAX_TOKENS_RANGE, value=int(raw.get("max_tokens") or 2048),
                                 key=f"tp_mt_{tid}", disabled=not mt_on)
            to_on = c3.checkbox("Custom timeout", value=bool(raw.get("timeout_s")), key=f"tp_so_{tid}")
            to = c3.number_input("Timeout (s)", *SAFE_TIMEOUT_RANGE, value=int(raw.get("timeout_s") or 90),
                                 key=f"tp_s_{tid}", disabled=not to_on)
            prof.update(temperature=temp if temp_on else None, max_tokens=int(mt) if mt_on else None,
                        timeout_s=int(to) if to_on else None)
            if use_custom or use_fb or temp_on or mt_on or to_on:
                new[tid] = prof
    c1, c2 = st.columns(2)
    if c1.button("Save task profiles", type="primary", key="tp_save"):
        save_prefs(profiles=new)
        st.toast("Task profiles saved to this session.")
        st.rerun()
    if c2.button("Reset all to defaults", key="tp_reset"):
        save_prefs(profiles={})
        for k in [k for k in st.session_state if k.startswith("tp_")]:
            del st.session_state[k]
        st.rerun()
    st.markdown("#### Saved configurations")
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    name = c1.text_input("Name", key="tp_cfg_name", max_chars=60, placeholder="Budget setup")
    if c2.button("Save current", key="tp_cfg_save") and name.strip():
        configs = [c for c in ctx.prefs["saved_configs"] if c["name"] != name.strip()]
        configs.append({"name": name.strip(), "profiles": current})
        save_prefs(saved_configs=configs[-10:])
        st.rerun()
    for cfg in ctx.prefs["saved_configs"]:
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.write(cfg["name"])
        if c2.button("Load", key=f"tp_ld_{cfg['name']}"):
            save_prefs(profiles=cfg["profiles"])
            for k in [k for k in st.session_state if k.startswith("tp_")]:
                del st.session_state[k]
            st.rerun()
        if c3.button("Delete", key=f"tp_dl_{cfg['name']}"):
            save_prefs(saved_configs=[c for c in ctx.prefs["saved_configs"] if c["name"] != cfg["name"]])
            st.rerun()


def _comparison(ctx: Ctx) -> None:
    st.write(f"Run one prompt on up to {cmp.MAX_MODELS} models side by side. Each model gets one attempt; "
             "tokens and cost are shown only when the provider reports them or you entered prices.")
    usable = [p for p in PROVIDERS if ctx.keys[p]]
    if not usable:
        st.info("Add at least one provider key in the API Keys tab.")
        return
    refs: list[ModelRef] = []
    n = st.slider("Models to compare", 2, cmp.MAX_MODELS, 2, key="cmp_n")
    cols = st.columns(n)
    for i, col in enumerate(cols):
        with col:
            prov = st.selectbox(f"Provider {i + 1}", usable, key=f"cmp_p{i}")
            model = _model_picker(f"Model {i + 1}", prov, "", f"cmp_m{i}", _default_model(ctx, prov))
            refs.append(ModelRef(prov, model.strip() or PROVIDERS[prov].default_model))
    preset = st.selectbox("Test prompt", [*cmp.TEST_PROMPTS, "Custom"], key="cmp_preset")
    prompt = st.text_area("Prompt", value=cmp.TEST_PROMPTS.get(preset, ""), key=f"cmp_prompt_{preset}",
                          max_chars=cmp.MAX_PROMPT_CHARS, height=90)
    if st.button("Run comparison", type="primary", key="cmp_run", icon=":material/compare_arrows:"):
        try:
            with st.spinner("Running models in parallel…"):
                st.session_state.compare_rows = cmp.run_comparison(
                    refs, prompt, lambda prov: ctx.keys.get(prov, ""), record=ctx.ws.record_usage)
        except ValueError as exc:
            st.warning(str(exc))
    rows = st.session_state.compare_rows
    if rows:
        from ..ai.usage import estimate_cost, price_key
        table = []
        for r in rows:
            cost = estimate_cost(r.in_tokens, r.out_tokens, ctx.prefs["pricing"].get(price_key(r.ref.provider, r.ref.model)))
            table.append({"Model": str(r.ref), "OK": "yes" if r.ok else "no", "Latency (ms)": r.latency_ms,
                          "Tokens in": r.in_tokens, "Tokens out": r.out_tokens,
                          "Est. cost (USD)": f"{cost:.5f}" if cost is not None else "—"})
        st.dataframe(table, hide_index=True, use_container_width=True)
        cols = st.columns(len(rows))
        for col, r in zip(cols, rows):
            with col:
                st.markdown(f"**{r.ref}**")
                if r.ok:
                    st.write(r.output)
                else:
                    st.error(r.error)


def _keys(ctx: Ctx) -> None:
    st.warning("Keys you paste here are held in this session's server memory only. They are not written to disk, "
               "logs, URLs or backups, and are never shown again after saving. Do not paste keys on a shared or "
               "untrusted device. For a personal deployment, prefer Streamlit **Secrets** (see README).",
               icon=":material/lock:")
    ss = st.session_state
    for svc in (*PROVIDERS, "TMDB"):
        key = ctx.tmdb_key if svc == "TMDB" else ctx.keys[svc]
        src = ctx.tmdb_source if svc == "TMDB" else ctx.key_source.get(svc, "")
        label, _ = _status(ctx, svc)
        with st.container(border=True):
            st.markdown(f"**{svc}** · {label}" + (f" · `{credentials.mask(key)}` from {src}" if key else ""))
            with st.form(f"key_form_{svc}", clear_on_submit=True, border=False):
                c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
                value = c1.text_input("API key" if svc != "TMDB" else "TMDB API key (v3 key or v4 token)",
                                      type="password", key=f"key_in_{svc}", autocomplete="off",
                                      placeholder="Paste a new key" if key else "Paste your key",
                                      help=PROVIDERS[svc].key_hint if svc in PROVIDERS else "themoviedb.org → Settings → API")
                saved = c2.form_submit_button("Save for session", use_container_width=True)
            if saved:
                v = (value or "").strip()
                if not v:
                    st.warning("Nothing to save.")
                elif len(v) < 8 or any(ch.isspace() for ch in v):
                    st.error("That doesn't look like an API key (too short or contains spaces).")
                else:
                    ss.api_keys[svc] = v
                    ss.key_status.pop(svc, None)
                    st.rerun()
            b1, b2 = st.columns(2)
            if b1.button("Test connection", key=f"key_test_{svc}", disabled=not key):
                _test(ctx, svc)
            if svc in ss.api_keys and b2.button("Remove session key", key=f"key_rm_{svc}"):
                ss.api_keys.pop(svc, None)
                ss.key_status.pop(svc, None)
                st.rerun()
    if st.button("Clear all session keys", key="keys_clear"):
        ss.api_keys.clear()
        ss.key_status.clear()
        st.rerun()


def _preferences(ctx: Ctx) -> None:
    p = ctx.prefs
    st.markdown("#### Analysis")
    c1, c2, c3 = st.columns(3)
    depth = c1.selectbox("Analysis depth", P.DEPTHS, index=P.DEPTHS.index(p["analysis_depth"]), key="pf_depth")
    length = c2.selectbox("Response length", P.LENGTHS, index=P.LENGTHS.index(p["response_length"]), key="pf_len")
    structure = c3.selectbox("Output structure", P.STRUCTURES, index=P.STRUCTURES.index(p["output_structure"]),
                             key="pf_struct")
    c1, c2, c3 = st.columns(3)
    language = c1.selectbox("Language", LANGUAGES, index=LANGUAGES.index(p["language"]), key="pf_lang")
    level = c2.selectbox("Spoiler protection", spoilers.LEVELS, index=spoilers.LEVELS.index(p["spoiler_level"]),
                         format_func=lambda x: spoilers.LABELS[x], key="pf_spoil")
    scale = c3.selectbox("Score scale", SCORE_SCALES, index=SCORE_SCALES.index(p["score_scale"]),
                         format_func=lambda s: f"0–{s}", key="pf_scale")
    cre_on = st.checkbox("Set creativity (temperature) for free-text tasks", value=p["creativity"] is not None, key="pf_co")
    cre = st.slider("Creativity", 0.0, 1.0, float(p["creativity"] if p["creativity"] is not None else 0.3), 0.05,
                    key="pf_cre", disabled=not cre_on)
    st.markdown("#### Category weights")
    st.caption("Used for the weighted score on critiques, battles and award nights. Stored scores are never changed.")
    cols = st.columns(4)
    weights = {k: cols[i % 4].slider(t, 0.0, MAX_WEIGHT, float(p["weights"][k]), 0.25, key=f"pf_w_{k}")
               for i, (k, t) in enumerate(DIMENSIONS)}
    st.markdown("#### Reliability")
    c1, c2, c3 = st.columns(3)
    timeout = c1.number_input("Default request timeout (s)", *SAFE_TIMEOUT_RANGE, value=int(p["request_timeout_s"]), key="pf_to")
    retries = c2.number_input("Max attempts per request", 1, 4, int(p["max_retries"]), key="pf_rt",
                              help="Retries apply only to temporary failures (rate limits, timeouts, outages).")
    save_chats = c3.toggle("Keep Ask the Critic chats in my session workspace", value=p["save_chats"], key="pf_chats")
    st.markdown("#### Usage limits and budget (optional)")
    c1, c2, c3 = st.columns(3)
    daily = c1.number_input("Daily request limit (0 = off)", 0, 1_000_000, int(p["daily_request_limit"]), key="pf_dl")
    budget = c2.number_input("Monthly budget USD (0 = off)", 0.0, 100000.0, float(p["monthly_budget_usd"]), 1.0, key="pf_mb")
    alert = c3.slider("Alert at % of limit", 10, 100, int(p["alert_threshold_pct"]), key="pf_al")
    hard = st.toggle("Stop sending AI requests when the estimated monthly budget is reached", value=p["hard_budget_stop"],
                     key="pf_hard", help="Spend is estimated from the prices below, so it only counts priced models.")
    st.markdown("#### Model prices (USD per 1M tokens, entered by you)")
    st.caption("CineCritic does not know current prices. Add them from your provider's pricing page to see cost estimates.")
    price_rows = [{"model": k, "input": v["in"], "output": v["out"]} for k, v in p["pricing"].items()]
    edited = st.data_editor(price_rows or [{"model": "", "input": 0.0, "output": 0.0}], num_rows="dynamic",
                            key="pf_price", use_container_width=True,
                            column_config={"model": st.column_config.TextColumn("Provider:model, e.g. OpenAI:gpt-4o-mini")})
    if st.button("Save preferences", type="primary", key="pf_save"):
        pricing = {str(r["model"]).strip(): {"in": r.get("input") or 0.0, "out": r.get("output") or 0.0}
                   for r in edited if str(r.get("model") or "").strip()}
        save_prefs(analysis_depth=depth, response_length=length, output_structure=structure, language=language,
                   spoiler_level=level, score_scale=scale, creativity=cre if cre_on else None, weights=weights,
                   request_timeout_s=timeout, max_retries=retries, save_chats=save_chats, daily_request_limit=daily,
                   monthly_budget_usd=budget, alert_threshold_pct=alert, hard_budget_stop=hard, pricing=pricing)
        for k in ("sc_scale", "sc_weights", "bt_scale", "bt_weights"):
            st.session_state.pop(k, None)
        st.toast("Preferences saved to this session.")
        st.rerun()


def render() -> None:
    ctx = get_ctx()
    header("AI Control Center", "Providers, models, task routing, keys and preferences in one place.")
    tabs = st.tabs(["Overview", "Providers", "Models", "Task Profiles", "Model Comparison", "API Keys",
                    "Analysis Preferences"])
    for tab, fn in zip(tabs, (_overview, _providers, _models, _profiles, _comparison, _keys, _preferences)):
        with tab:
            fn(ctx)
