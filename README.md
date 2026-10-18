# CineCritic

React + TypeScript frontend (Vite) with TypeScript serverless functions in `api/`, built for Vercel.

## API keys

Open **Settings** in the app and paste a TMDB key plus a key for Gemini, OpenAI, Anthropic or Mistral. Keys are saved only in the visitor's browser and sent with each request. Nothing is stored on the server.

## Environment variables (all optional)

Set these only if you want the server to supply default keys when a visitor hasn't entered their own.

| Name | Purpose |
|---|---|
| `TMDB_API_KEY` | TMDB v3 key or v4 read token |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `MISTRAL_API_KEY` | AI provider (first one found is used) |
| `AI_PROVIDER` | `anthropic`, `openai`, `gemini` or `mistral` |
| `AI_MODEL` | Override the default model |

## Run locally

```bash
npm install
# optional: cp .env.example .env.local
npx vercel dev
```

Open http://localhost:3000. `npx vercel dev` serves the frontend and the `/api` functions together. `npm run dev` starts only the frontend.

## Check

```bash
npm test
npm run typecheck
npm run build
```

## Deploy

1. Push this folder to a GitHub repository.
2. In Vercel, choose Add New, then Project, and import the repository. The Vite preset is detected automatically.
3. Environment variables are optional. Visitors add their own keys in Settings.
4. Click Deploy.

Or from the terminal: `npx vercel`, then `npx vercel --prod`.
