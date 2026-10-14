# CineCritic 3.0 — AI Cinema Intelligence

Premium film critique, discovery and analysis built with **Python, Streamlit and LangChain**, designed for
**Streamlit Community Cloud**. Visual identity: *Cinema Noir Intelligence* (Bebas Neue + Inter, gold and burgundy on obsidian).

**No database.** Every visitor gets an in-memory workspace for the current session. Preferences, archive,
analyses, quests, chats and usage live in `st.session_state` and are lost when the session ends — unless the
user downloads a JSON backup from the sidebar and restores it later. API keys are never part of a backup.

## Pages

| Section | Page | What it does |
|---|---|---|
| Cinema | Cinema Home | Search entry, latest dossier, quick access, recent dossiers (real session data only) |
| | Film Critique | Observable pipeline, eight craft scorecards, spoiler gate, exports (PDF/JSON) |
| | Film Discovery | TMDB listings and filters, AI taste picks, plain-English filters |
| | Smart Movie Search | TMDB title search with refinements; "describe a film" recall verified on TMDB |
| Intelligence | Ask the Critic | Chat grounded in your analyses, spoiler-aware |
| | Film Intelligence Graph | Connections with stated reasons; verified vs AI-inferred; table fallback |
| | Head-to-Head Movie Battles | Deterministic category tally with tie/inconclusive handling |
| My Cinema | Personal Film Archive | Status, ratings, reviews, notes, favourites; CSV/JSON/PDF; Award Nights |
| | Discovery Quests | Genre, decades, world cinema, director, franchise quests |
| System & AI | AI Control Center | Overview, providers, model discovery, task profiles with fallback, model comparison, API keys, preferences |
| | Pipeline Monitor | Every run, stage by stage, with model request lifecycle |
| | Diagnostics | Health checks, self-tests, caches, safe report |
| | API Usage Monitor | Local request counts, tokens when reported, latency, retries, estimated cost from your prices, limits |

Providers: Gemini, OpenAI, Anthropic, Mistral (via LangChain). Film data: TMDB.

## Run locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then fill in your keys (file is git-ignored)
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). In short: push to GitHub, create the app with `app.py` as the entry
point, paste your keys into **Settings → Secrets**, deploy.

## Security model

- Deployment keys come from Streamlit Secrets or environment variables (read-only).
- Keys pasted in the app live in that session's server memory only; they are masked after saving, are not written to
  disk, logs, URLs, usage events, error reports or backups, and are not encrypted at rest (they are never at rest).
- Errors are classified and redacted before display; usage events never store prompts or responses.

## Spoilers

Default is spoiler-free. Prompts instruct the model accordingly, a sentence-level filter removes outcome language
from the main fields, and any spoiler text is kept in a separate field that the UI shows only after an explicit
*Reveal* click. The filter is heuristic: it reduces spoiler risk but cannot guarantee zero spoilers.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Backend tests use fake models and make no network calls. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for what is
and is not covered.

## Attribution

This product uses the TMDB API but is not endorsed or certified by TMDB. AI scores are subjective assessments, not
ratings from IMDb, TMDB or any audience.
