# CineCritic

React + TypeScript frontend (Vite) with TypeScript serverless functions in `api/`, built for Vercel.

## Providers

Gemini, OpenAI, Anthropic, Mistral and Hugging Face. Pick one in **Settings**, paste its key, choose a model, test the connection, then save.

- **Model list.** Fetched live from the provider with your key where the provider offers a list. If it can't be loaded, only CineCritic's suggested default is shown and labelled as such. Hugging Face has no default: choose a model.
- **Compatibility.** Shown only when the provider reports it. Otherwise a model is marked "Unverified". Test connection is the real check.
- **Hugging Face.** Uses the Inference Providers router (`https://router.huggingface.co/v1`) with a fine-grained token that has the "Make calls to Inference Providers" permission. Only models served by an inference provider work. Add `:fastest`, `:cheapest` or a provider name to a model ID to choose routing. Pricing, quotas and latency vary by model and provider and are not shown here.
- **Saved default.** Selecting a model changes nothing until you press Save. The app never switches models on its own.

## How keys are stored

Keys live in your browser. By default they are kept for the tab session only (`sessionStorage`). Tick "Remember keys on this device" to keep them in `localStorage`. Browser storage is not encrypted: scripts or extensions on the site and anyone using the device can read it. Each request sends the keys over HTTPS to this site's server, which uses them for that request only and does not store or log them. Use restricted keys with spending limits. Users upgrading from an older version have their saved keys migrated and kept on the device.

## Pipeline

Critique, Discover, Ask, Battle and Test connection stream newline-delimited JSON from their endpoint: `event` messages (one per stage change), then a final `result` or `error`. Each event carries `executionId`, `operation`, `stageId`, `stageLabel`, `status`, `timestamp`, `seq`, `message`, `retryCount`, and optionally `progress`, `duration`, `errorCode`, `provider`, `model`. Progress is only sent where it is countable, such as "2 of 6 films verified". Overall progress is shown as "n of m stages".

The **Monitor** page lists recent runs (last 40, stored in this browser, without keys, prompts or retry data) with per-stage timings, retries, provider and model.

Reliability: one retry for rate limits, provider outages and network errors; one retry for empty or unreadable AI output; a 55 second server deadline; a 75 second client guard; Cancel aborts the browser request. Errors are typed, sanitised and carry a next step and a short reference.

## Environment variables (all optional)

Set these only if you want the server to supply defaults when a visitor hasn't entered their own.

| Name | Purpose |
|---|---|
| `TMDB_API_KEY` | TMDB v3 key or v4 read token |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `MISTRAL_API_KEY`, `HF_TOKEN` | AI provider (first found in that order is used) |
| `AI_PROVIDER` | `anthropic`, `openai`, `gemini`, `mistral` or `huggingface` |
| `AI_MODEL` | Model to use with the server key (required for Hugging Face) |

## Run locally

```bash
npm install
npx vercel dev
```

Open http://localhost:3000. `npm run dev` starts only the frontend.

## Check

```bash
npm test
npm run typecheck
npm run build
```

## Deploy

Push to GitHub, import the repository in Vercel (the Vite preset is detected), and deploy. Environment variables are optional. Functions are limited to 60 seconds (`vercel.json`).

## Known limits

- Cancel stops the browser's request. Whether the provider stops generating depends on the platform propagating the disconnect.
- Run history is per browser.
- Streaming responses depend on Vercel's Node functions supporting streamed Web `Response` bodies.
