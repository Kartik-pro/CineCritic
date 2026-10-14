# Deploying CineCritic on Streamlit Community Cloud

1. Push the repository to GitHub (never commit `.env` or `.streamlit/secrets.toml`; both are git-ignored).
2. At share.streamlit.io choose **Create app**, select the repository and branch, and set the main file to `app.py`.
3. Under **Advanced settings → Secrets** paste the contents of `.streamlit/secrets.toml.example` with your real keys.
   You need at least one AI provider key. A TMDB key is needed for discovery, search, posters and verified credits.
4. Deploy. `packages.txt` installs a Unicode font so PDF exports can render non-Latin text.
5. After the first successful build, run `pip freeze` in the same Python version (or read the build log) and pin the
   versions in `requirements.txt`.

## Behaviour to expect

- **No persistence.** Community Cloud restarts, sleeps and redeploys discard session data. Users should download a
  backup (sidebar) to keep their archive.
- **Shared server, separate sessions.** Each visitor has their own workspace and keys; nothing is shared.
- **Free-tier limits.** Provider quotas and Community Cloud resources apply. The app retries only temporary failures,
  pauses a failing provider briefly, and never switches models silently.
- **Keys.** Prefer Secrets. Keys typed into AI Control Center last only for that session.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "No <provider> API key is configured" | Secret name mismatch. Use the names in `secrets.toml.example`. |
| "needs the `langchain-…` package" | Provider package missing from `requirements.txt`. |
| Posters/credits missing | No TMDB key, or TMDB rate limit. |
| PDF shows `?` for some characters | Font package missing; the app falls back to a Latin-1 font. |
