# Architecture

```
app.py                      st.navigation (4 sections), sidebar workspace backup, footer
cinecritic/
  views/                    one module per page (UI only; no provider or prompt logic)
  ui/                       state, runtime (main-thread Ctx), live pipeline, shared widgets, HTML components, CSS
  ai/                       providers (build + discovery), gateway (profiles, retry, fallback, breaker), usage
  features/                 ask, battles, graph, quests, awards, compare_models, monitoring, exports, serialize
  storage/workspace.py      in-memory workspace + JSON backup/restore (no database)
  services.py, metadata.py  analysis/discovery pipelines; TMDB client with caches
  prompts.py, schemas.py, spoilers.py, scoring.py, prefs.py, credentials.py, errors.py, pipeline.py, config.py
```

## Boundaries

- Backend modules never import Streamlit. UI modules never build provider clients or prompts.
- `st.session_state` is unavailable in worker threads, so `ui/runtime.get_ctx()` snapshots keys, preferences and the
  gateway on the main thread; pipelines run in a worker while the main thread redraws real stage state (`ui/live.py`).
- Navigation: buttons call `goto()`, which stores a request; `app.py` serves it with `st.switch_page`.

## Integration contract mapping (CINECRITIC-IC-1.0)

The repository already had its own interfaces, so they were kept and mapped rather than duplicated:
`AppError` + categories = normalized error contract; `PipelineRun` = pipeline events; `Gateway.call` = routing and
fallback; task ids are `analysis, quick, recommend, search_assist, summarize, extract, ask` (the contract's example
names `critic_chat`/`movie_comparison` map to `ask`/`summarize`); usage events record source-labelled local data.

## Feature inventory (honest status)

| Feature | Status | Notes |
|---|---|---|
| All 13 pages | working under a fake-Streamlit smoke test | Not yet run in real Streamlit |
| Backend logic | 133 automated tests pass (fake models, no network) | Real provider/TMDB calls unverified here |
| Spoiler protection | working, heuristic | Cannot guarantee zero spoilers |
| Persistence | session only + JSON backup | By design (no database) |
| LangGraph | not used | No multi-step stateful workflow needed |
| Pipeline "cancelled" state | not applicable | Runs cannot be cancelled |
| Mobile layout | CSS written, not visually verified | |
