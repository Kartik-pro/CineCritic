"""Main-thread snapshot of everything a request needs (preferences, keys, gateway).

st.session_state is not readable from worker threads, so pages build a Ctx here, on the main thread,
and hand plain values to the pipeline. Keys are held in the Ctx only for the duration of a rerun.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from .. import credentials, prefs as prefs_mod
from ..ai.gateway import Gateway
from ..ai.providers import resolve_key
from ..config import PROVIDERS, TMDB_ENV_VAR
from ..env_manager import get_server_key
from ..features import monitoring
from ..storage.workspace import Workspace
from .state import workspace


@dataclass
class Ctx:
    ws: Workspace
    prefs: dict
    keys: dict[str, str]              # provider label -> key in use
    key_source: dict[str, str]        # provider label -> 'session' | 'secrets/env' | ''
    tmdb_key: str
    tmdb_source: str
    statuses: dict
    gateway: Gateway
    secrets: list[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        return self.prefs["spoiler_level"]

    def configured(self, provider: str) -> bool:
        return bool(self.keys.get(provider))


def get_prefs(ws: Workspace | None = None) -> dict:
    return prefs_mod.validate((ws or workspace()).prefs)


def save_prefs(**changes) -> dict:
    """Validate and store preference changes in the session workspace."""
    ws = workspace()
    merged = prefs_mod.validate({**get_prefs(ws), **changes})
    for k, v in merged.items():
        ws.set_pref(k, v)
    return merged


def get_ctx() -> Ctx:
    ss = st.session_state
    ws = workspace()
    p = get_prefs(ws)
    keys, sources = {}, {}
    for label, provider in PROVIDERS.items():
        keys[label], sources[label] = resolve_key(provider, ss.api_keys)
    tmdb = (ss.api_keys.get("TMDB") or "").strip()
    tmdb_source = "session" if tmdb else ""
    if not tmdb:
        tmdb = get_server_key(TMDB_ENV_VAR)
        tmdb_source = "secrets/env" if tmdb else ""
    statuses = dict(ss.key_status)

    def pre(ref, key):
        return credentials.preflight_error(ref.provider, ref.model, key, statuses.get(ref.provider))

    gateway = Gateway(
        profile_for=lambda t: prefs_mod.resolve_profile(p, t),
        key_for=lambda prov: keys.get(prov, ""),
        record=ws.record_usage, preflight=pre,
        over_budget=lambda: monitoring.over_budget(ws.usage_events(), p),
        breaker=ss.breaker, max_attempts=p["max_retries"])
    secrets = [k for k in (*keys.values(), tmdb) if k]
    return Ctx(ws, p, keys, sources, tmdb, tmdb_source, statuses, gateway, secrets)
