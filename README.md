# CineCritic

**An AI-powered cinema companion for discovering, analysing, and comparing films.**

CineCritic combines movie metadata from [The Movie Database (TMDB)](https://www.themoviedb.org/) with AI-powered film analysis. Search for a film, explore recommendations, get a structured critique, ask questions about a movie, compare two titles, and keep a personal watchlist.

> CineCritic is an independent project. TMDB and the supported AI providers are third-party services; their API access, usage limits, and pricing apply.

## Features

- **Film search** — find movies using TMDB data, including titles, posters, summaries, and related metadata.
- **AI critique** — generate a structured analysis of a film, with craft-focused scoring and written commentary.
- **Discover** — explore films and get AI-assisted discovery suggestions.
- **Ask the Critic** — ask questions about a selected movie.
- **Movie Battles** — compare two films and explore their differences.
- **Personal watchlist** — maintain a list of films you want to track.
- **Spoiler-aware analysis** — spoiler handling is implemented in the shared server logic; check the selected analysis mode and settings before reading detailed discussion.
- **Provider settings** — configure supported AI providers and model preferences.
- **API status endpoint** — check service configuration through the status API.

## Tech stack

| Layer | Technologies |
|---|---|
| Frontend | React 19, TypeScript, Vite 7 |
| Backend | TypeScript serverless API routes |
| Movie data | TMDB API |
| AI providers | Anthropic, OpenAI, Google Gemini, Mistral |
| Hosting | Vercel |
| Testing | Node test runner via `tsx`, TypeScript checks |

The project targets **Node.js 20 or newer**.

## Project structure

```text
.
├── api/                   # Vercel serverless API endpoints
│   ├── ask.ts
│   ├── compare.ts
│   ├── critique.ts
│   ├── discover.ts
│   ├── movies.ts
│   └── status.ts
├── server/                # Server-side AI, TMDB, prompts and safety logic
│   ├── ai.ts
│   ├── context.ts
│   ├── critique.ts
│   ├── http.ts
│   ├── keys.ts
│   ├── prompts.ts
│   ├── spoilers.ts
│   └── tmdb.ts
├── shared/                # Shared types and scoring utilities
├── src/
│   ├── components/        # Reusable UI components
│   ├── pages/             # Critique, Discover, Ask, Battle, Watchlist, Settings
│   ├── App.tsx
│   ├── api.ts
│   └── state.tsx
├── tests/                 # API, scoring and spoiler tests
├── public/
├── index.html
├── package.json
├── vercel.json
└── vite.config.mts
```

## Getting started

### Requirements

- Node.js 20+
- npm
- A TMDB API key
- An API key for at least one supported AI provider, unless you configure server-side default keys

### 1. Clone the repository

```bash
git clone https://github.com/Kartik-pro/CineCritic.git
cd CineCritic
npm install
```

### 2. Configure API keys

CineCritic supports two configuration approaches:

**Option A — Enter keys in the app**

Open **Settings** and enter your TMDB key and the key for your chosen AI provider. The current app stores visitor-entered keys in the browser and sends them with relevant requests; they are not saved as server environment variables.

**Option B — Configure server-side defaults**

Copy `.env.example` to `.env.local` and set the values you want the server to use as defaults:

```dotenv
TMDB_API_KEY=your_tmdb_api_key
GOOGLE_API_KEY=your_google_api_key
AI_PROVIDER=gemini
AI_MODEL=gemini-3.5-flash
```

Use the provider key matching your selection:

| Variable | Purpose |
|---|---|
| `TMDB_API_KEY` | TMDB API key or supported read token |
| `GOOGLE_API_KEY` | Google Gemini |
| `OPENAI_API_KEY` | OpenAI |
| `ANTHROPIC_API_KEY` | Anthropic |
| `MISTRAL_API_KEY` | Mistral |
| `AI_PROVIDER` | Default provider: `gemini`, `openai`, `anthropic`, or `mistral` |
| `AI_MODEL` | Optional model override |

Environment variables are optional when visitors provide their own keys in Settings. To enable server-provided defaults, configure the relevant variables in your local environment or Vercel project settings.

**Security:** never commit real API keys. Keep server secrets out of frontend source code and do not use a `VITE_` prefix for private keys. If you deploy with server-side defaults, users of that deployment may be able to use those configured services, so monitor provider usage and limits.

### 3. Run locally

For frontend-only development:

```bash
npm run dev
```

Vite will print the local development URL. This starts the frontend only; API calls need the backend routes to be available.

To run the frontend and Vercel API routes together:

```bash
npx vercel dev
```

Open the local URL printed by Vercel CLI (typically `http://localhost:3000`). Make sure your local environment variables are loaded for server-side defaults.

## Quality checks

Run the available checks before submitting changes:

```bash
npm test
npm run typecheck
npm run build
```

- `npm test` — runs the test suite.
- `npm run typecheck` — checks TypeScript types.
- `npm run build` — creates the production frontend build in `dist/`.

## Deploy to Vercel

1. Push the repository to GitHub.
2. Open [Vercel](https://vercel.com/) and select **Add New → Project**.
3. Import `Kartik-pro/CineCritic`.
4. Use these build settings:

   | Setting | Value |
   |---|---|
   | Framework Preset | Vite |
   | Root Directory | `./` |
   | Install Command | `npm install` |
   | Build Command | `npm run build` |
   | Output Directory | `dist` |

5. If you want server-side default keys, add the required environment variables under **Project Settings → Environment Variables**. At minimum, add `TMDB_API_KEY` and one AI provider key, then optionally set `AI_PROVIDER` and `AI_MODEL`. If visitors will enter their own keys in Settings, server-side defaults can be omitted.
6. Deploy.

The repository includes `vercel.json`, which configures the maximum duration for API functions under `api/*.ts`.

You can also deploy from a terminal with the Vercel CLI:

```bash
npx vercel
npx vercel --prod
```

## API routes

| Route | Purpose |
|---|---|
| `/api/movies` | Movie search and metadata |
| `/api/critique` | AI-powered film critique |
| `/api/discover` | Film discovery |
| `/api/ask` | Ask questions about a film |
| `/api/compare` | Compare two films |
| `/api/status` | Service/configuration status |

## Contributing

Issues and pull requests are welcome. For changes:

1. Create a branch for your work.
2. Keep API keys and other secrets out of commits.
3. Run `npm test`, `npm run typecheck`, and `npm run build`.
4. Describe the change and any relevant testing in your pull request.

## License

See [LICENSE](./LICENSE) for the project's license.
