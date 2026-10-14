"""Run a pipeline in a worker thread while the main thread redraws real execution state."""
from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

import streamlit as st

from ..errors import AppError, classify
from ..pipeline import PipelineRun
from .components import compact, events_html, pipeline_html
from .state import workspace

T = TypeVar("T")


def run_live(run: PipelineRun, work: Callable[[], T], *, secrets: list[str], slot=None) -> tuple[T | None, AppError | None]:
    """Execute `work()` (which must not touch st.*) and animate `run` until it ends.

    Returns (result, None) or (None, classified error). The run is logged to the Pipeline Monitor
    whatever the outcome. Exceptions never propagate, so a failure cannot blank the page.
    """
    slot = slot if slot is not None else st.empty()
    box: dict = {}

    def target() -> None:
        try:
            box["result"] = work()
        except BaseException as exc:  # noqa: BLE001 - surfaced as a classified error below
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    while thread.is_alive():
        slot.markdown(compact(pipeline_html(run)), unsafe_allow_html=True)
        time.sleep(0.3)
    thread.join()
    if run.overall == "running":
        run.finish()
    slot.markdown(compact(pipeline_html(run)), unsafe_allow_html=True)
    log_run(run)
    err = box.get("error")
    if err is None:
        return box.get("result"), None
    app_err = err if isinstance(err, AppError) else classify(err, source="ai", secrets=secrets)
    return None, app_err


def log_run(run: PipelineRun) -> None:
    s = run.summary()
    workspace().log_run(run_id=s["run_id"], kind=s["kind"], label=s["label"], status=s["status"],
                        duration_s=s["duration_s"], model=s["model"], retries=s["retries"],
                        error_category=s["error_category"], stages=s["stages"])
    st.session_state.last_run = run


def show_events(run: PipelineRun | None) -> None:
    if run is not None:
        html = events_html(run)
        if html:
            with st.expander("Execution events"):
                st.markdown(compact(html), unsafe_allow_html=True)
