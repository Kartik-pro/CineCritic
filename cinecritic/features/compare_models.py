"""Repeatable model comparison: same prompt, measured latency and tokens, side-by-side output.

Everything shown comes from real measurements of the calls made here. Context windows and costs are
reported separately (provider-reported / user-configured) by the page, never invented.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from ..ai.providers import ModelRef, build_llm
from ..ai.usage import UsageCollector
from ..errors import AppError, classify
from ..pipeline import call_with_retries
from ..services import to_text

TEST_PROMPTS = {
    "Craft explainer": "In three sentences, explain what a Dutch angle is and name one real film that uses it well.",
    "Spoiler-free pitch": "Write a two-sentence, completely spoiler-free pitch for the film Parasite (2019).",
    "Critic voice": "In 60 words, critique the cinematography of Blade Runner 2049 without revealing the plot.",
}
MAX_PROMPT_CHARS = 600
MAX_MODELS = 4


@dataclass(frozen=True)
class ComparisonRow:
    ref: ModelRef
    ok: bool
    latency_ms: int
    in_tokens: int | None
    out_tokens: int | None
    output: str
    error: str = ""
    category: str = ""


def run_comparison(refs: list[ModelRef], prompt: str, key_for: Callable[[str], str], *,
                   builder=build_llm, record: Callable[..., None] | None = None) -> list[ComparisonRow]:
    """Run `prompt` on each model (in parallel, one attempt each). Never raises for a single failure."""
    prompt = (prompt or "").strip()[:MAX_PROMPT_CHARS]
    if not prompt:
        raise ValueError("Enter a test prompt.")
    refs = list(dict.fromkeys(refs))[:MAX_MODELS]

    def one(ref: ModelRef) -> ComparisonRow:
        key = key_for(ref.provider)
        collector = UsageCollector()
        started = time.perf_counter()
        try:
            llm = builder(ref, key)
            text = call_with_retries(lambda: to_text(llm.invoke(prompt, config={"callbacks": [collector]}).content),
                                     stage="compare", source="ai", secrets=[key], provider_label=ref.provider,
                                     max_attempts=1)
            row = ComparisonRow(ref, True, int((time.perf_counter() - started) * 1000), collector.input_tokens,
                                collector.output_tokens, text.strip())
        except Exception as exc:
            err = exc if isinstance(exc, AppError) else classify(exc, stage="compare", source="ai", secrets=[key],
                                                                 provider_label=ref.provider)
            row = ComparisonRow(ref, False, int((time.perf_counter() - started) * 1000), None, None, "",
                                err.message, err.category.value)
        if record is not None:
            try:
                record(provider=ref.provider, model=ref.model, task="comparison", ok=row.ok, latency_ms=row.latency_ms,
                       in_tokens=row.in_tokens, out_tokens=row.out_tokens, error_category=row.category,
                       error_message=row.error)
            except Exception:
                pass
        return row

    with ThreadPoolExecutor(max_workers=len(refs) or 1) as pool:
        return list(pool.map(one, refs))
