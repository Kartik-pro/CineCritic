"""User preferences and per-task model profiles: defaults, validation and resolution.

Pure Python (no Streamlit). Everything coming from the UI or a restored backup passes through
`validate`, which clamps values to safe ranges and drops unknown keys.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .ai.providers import ModelRef
from .config import (
    DEFAULT_WEIGHTS, LANGUAGES, MAX_WEIGHT, PROVIDERS, SAFE_MAX_TOKENS_RANGE, SAFE_TIMEOUT_RANGE,
    SCORE_SCALES, SPOILER_LEVELS, TASKS,
)

DEPTHS = ("brief", "standard", "deep")
LENGTHS = ("concise", "balanced", "detailed")
STRUCTURES = ("scorecards first", "narrative first")

DEFAULTS: dict[str, Any] = {
    "analysis_depth": "standard",
    "response_length": "balanced",
    "creativity": None,           # temperature for free-text tasks; None = the model's own default
    "output_structure": "scorecards first",
    "spoiler_level": "none",      # spoiler-free by default
    "language": "English",
    "default_provider": "Gemini",
    "default_model": "",
    "score_scale": 10,
    "weights": dict(DEFAULT_WEIGHTS),
    "request_timeout_s": 90,
    "max_retries": 3,
    "profiles": {},               # task id -> profile dict (see PROFILE_DEFAULTS)
    "pricing": {},                # "Provider:model" -> {"in": usd per 1M tokens, "out": usd per 1M tokens}
    "daily_request_limit": 0,     # 0 = not configured
    "monthly_budget_usd": 0.0,    # 0 = not configured
    "hard_budget_stop": False,
    "alert_threshold_pct": 80,
    "save_chats": False,
    "saved_configs": [],
}

PROFILE_DEFAULTS: dict[str, Any] = {
    "provider": "", "model": "", "fallback_provider": "", "fallback_model": "",
    "temperature": None, "max_tokens": None, "timeout_s": None,
}


def _num(value, lo, hi, default):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(v, lo), hi)


def validate_profile(raw: Any) -> dict[str, Any]:
    p = dict(PROFILE_DEFAULTS)
    if not isinstance(raw, dict):
        return p
    for side in ("", "fallback_"):
        prov = str(raw.get(f"{side}provider") or "")
        if prov in PROVIDERS:
            p[f"{side}provider"] = prov
            p[f"{side}model"] = str(raw.get(f"{side}model") or "").strip()[:120]
    if raw.get("temperature") not in (None, ""):
        p["temperature"] = round(_num(raw["temperature"], 0.0, 1.0, 0.3), 2)
    if raw.get("max_tokens") not in (None, "", 0):
        p["max_tokens"] = int(_num(raw["max_tokens"], *SAFE_MAX_TOKENS_RANGE, 2048))
    if raw.get("timeout_s") not in (None, "", 0):
        p["timeout_s"] = int(_num(raw["timeout_s"], *SAFE_TIMEOUT_RANGE, 90))
    return p


def validate(raw: Any) -> dict[str, Any]:
    """Return a complete, safe preferences dict from arbitrary input."""
    out = copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        return out

    def pick(key, allowed):
        if raw.get(key) in allowed:
            out[key] = raw[key]

    pick("analysis_depth", DEPTHS)
    pick("response_length", LENGTHS)
    pick("output_structure", STRUCTURES)
    pick("spoiler_level", SPOILER_LEVELS)
    pick("language", LANGUAGES)
    pick("default_provider", tuple(PROVIDERS))
    pick("score_scale", SCORE_SCALES)
    out["default_model"] = str(raw.get("default_model") or "").strip()[:120]
    out["creativity"] = None if raw.get("creativity") in (None, "") else round(_num(raw["creativity"], 0.0, 1.0, 0.3), 2)
    out["request_timeout_s"] = int(_num(raw.get("request_timeout_s"), *SAFE_TIMEOUT_RANGE, DEFAULTS["request_timeout_s"]))
    out["max_retries"] = int(_num(raw.get("max_retries"), 1, 4, DEFAULTS["max_retries"]))
    out["daily_request_limit"] = int(_num(raw.get("daily_request_limit"), 0, 1_000_000, 0))
    out["monthly_budget_usd"] = round(_num(raw.get("monthly_budget_usd"), 0, 100_000, 0.0), 2)
    out["alert_threshold_pct"] = int(_num(raw.get("alert_threshold_pct"), 10, 100, 80))
    out["hard_budget_stop"] = bool(raw.get("hard_budget_stop"))
    out["save_chats"] = bool(raw.get("save_chats"))
    weights = raw.get("weights") if isinstance(raw.get("weights"), dict) else {}
    out["weights"] = {k: round(_num(weights.get(k), 0.0, MAX_WEIGHT, DEFAULT_WEIGHTS[k]), 2) for k in DEFAULT_WEIGHTS}
    if sum(out["weights"].values()) <= 0:
        out["weights"] = dict(DEFAULT_WEIGHTS)
    profiles = raw.get("profiles") if isinstance(raw.get("profiles"), dict) else {}
    out["profiles"] = {t: validate_profile(profiles[t]) for t in TASKS if t in profiles}
    pricing = raw.get("pricing") if isinstance(raw.get("pricing"), dict) else {}
    out["pricing"] = {str(k)[:160]: {"in": _num(v.get("in"), 0, 100000, 0.0), "out": _num(v.get("out"), 0, 100000, 0.0)}
                      for k, v in list(pricing.items())[:60] if isinstance(v, dict)}
    saved = raw.get("saved_configs") if isinstance(raw.get("saved_configs"), list) else []
    out["saved_configs"] = [{"name": str(c.get("name", ""))[:60], "profiles": {t: validate_profile(p) for t, p in
                             (c.get("profiles") or {}).items() if t in TASKS}}
                            for c in saved[:10] if isinstance(c, dict) and c.get("name")]
    return out


@dataclass(frozen=True)
class Profile:
    task: str
    primary: ModelRef
    fallback: ModelRef | None
    temperature: float | None
    max_tokens: int | None
    timeout_s: int


def resolve_profile(prefs: dict[str, Any], task: str) -> Profile:
    """Task override -> global default provider/model -> provider default model."""
    prefs = prefs or DEFAULTS
    p = (prefs.get("profiles") or {}).get(task) or {}
    provider = p.get("provider") or prefs.get("default_provider") or next(iter(PROVIDERS))
    if provider not in PROVIDERS:
        provider = next(iter(PROVIDERS))
    if p.get("provider"):
        model = p.get("model") or PROVIDERS[provider].default_model
    else:
        model = prefs.get("default_model") if provider == prefs.get("default_provider") else ""
        model = model or PROVIDERS[provider].default_model
    fallback = None
    if p.get("fallback_provider") in PROVIDERS:
        fp = p["fallback_provider"]
        fm = p.get("fallback_model") or PROVIDERS[fp].default_model
        if (fp, fm) != (provider, model):
            fallback = ModelRef(fp, fm)
    temperature = p.get("temperature")
    if temperature is None and TASKS[task].structured is False:
        temperature = prefs.get("creativity")
    return Profile(task, ModelRef(provider, model), fallback, temperature, p.get("max_tokens"),
                   p.get("timeout_s") or prefs.get("request_timeout_s", 90))
