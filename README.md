# 🎬 CineCritic

[![Vercel Deployment](https://shields.io)](https://vercel.app)
[![TypeScript](https://shields.io)](https://typescriptlang.org)
[![Vite](https://shields.io)](https://vite.dev)

An **AI-powered film analysis and cinema intelligence platform** built with React, TypeScript, and Vite. CineCritic brings AI-assisted movie critique, film discovery, conversational questions, movie battles, and multi-provider AI configuration into a single interface. 

Instead of hiding behind a generic loading spinner, CineCritic features a **live execution pipeline monitor** that surfaces real-time backend updates, metrics, and workflow transparently to the user.

---

## 🗺️ Architecture Diagram

Explore the full interactive visualization of the repository architecture directly via GitDiagram.

[![Architecture diagram of Kartik-pro/CineCritic](https://gitdiagram.com)](https://gitdiagram.com)

> 💡 *Click the diagram above to explore the interactive repository structural relationships.*

---

## ✨ Features

### 🎥 AI-Powered Film Workflows
* **Critique:** Run deep, AI-assisted film critiques.
* **Discover:** Explore new movies dynamically via tailored discovery flows.
* **Ask:** Chat directly with your configured AI provider about specific films.
* **Battle:** Compare two different films side-by-side using analytical metrics.
* **Connection Testing:** Run validation steps to verify your API credentials seamlessly.

### 🤖 Multi-Provider AI Support
Configure your own keys directly in-browser. Supported engines include:
* Google Gemini
* OpenAI
* Anthropic
* Mistral
* Hugging Face Inference Providers

### ⚡ Live Pipeline Monitoring
* **Transparent Execution:** Real-time visibility into active stages (e.g., "2 of 6 films verified").
* **Execution Status & Metrics:** Track countdowns, elapsed durations, retries, and errors.
* **Browser-Local Run Monitor:** Reviews the last 40 recorded executions in your browser with precise metrics without storing prompt details or keys.

---

## 🧰 Tech Stack

| Technology | Purpose |
| :--- | :--- |
| **React 19** | User interface components and reactive rendering |
| **TypeScript** | Strict type-safety across client-side code and API contracts |
| **Vite 7** | Lightning-fast local development server and optimized frontend builds |
| **Node.js 20+** | JavaScript runtime environment for tooling and functions |
| **Vercel Functions** | Serverless API endpoints handling streaming protocols |
| **AI Providers** | Native SDK integrations with Gemini, OpenAI, Anthropic, and Mistral |
| **Hugging Face** | Unified endpoint router (`https://huggingface.co`) |
| **TMDB API** | Optional source metadata connection for live film lookup validation |
| **tsx** | Direct execution engine for test suites |
| **Vercel Speed Insights** | Real-time production web performance and core web vitals tracking |

---

## 🏗️ System Architecture

### High-Level Request Flow
```text
┌─────────────────────┐
│       Browser       │
│  React + TypeScript │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│   User Interface    │
│ Settings & Workflows│
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│ Streaming API Calls │
│       NDJSON        │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│ TypeScript API      │
│ Routes in api/      │
└──────────┬──────────┘
           │
┌──────────┴─────────────┐
│                        │
┌───────▼────────┐      ┌───▼──────────────┐
│  AI Providers  │      │    Film Data     │
│Gemini / OpenAI │      │ TMDB (optional)  │
│Anthropic / etc.│      └──────────────────┘
└────────────────┘
                ┌──────────────────────┐
                │  Pipeline Monitoring │
                │ Browser-Local History│
                └──────────────────────┘
```

---

## 📁 Project Structure

```text
CineCritic/
├── api/                  # TypeScript serverless API endpoints (Vercel)
├── public/               # Static assets & public media assets
├── server/               # Shared backend utilities (adapters, context builder, prompt engines)
│   ├── providers/        # AI provider middleware & structural wrappers
│   ├── ai.ts             # Primary inference routing
│   ├── context.ts        # Context construction for models
│   ├── operations.ts     # Internal execution sequence orchestrator
│   ├── prompts.ts        # Prompt configurations & structural templates
│   └── tmdb.ts           # TMDB interface layer
├── shared/               # Pure type configurations and system protocols
│   ├── pipeline.ts       # Typed pipeline interfaces and NDJSON structures
│   ├── providers.ts      # Structured multi-provider schema profiles
│   └── scoring.ts        # Film comparison analytics parameters
├── src/                  # React Single Page Application (Vite project)
│   ├── components/       # Reusable layout UI components
│   ├── pages/            # View managers (Critique, Discover, Battle, Monitor, Settings, etc.)
│   ├── pipeline/         # Client-side stream parsers and runners
│   ├── keys.ts           # Browser credentials management core
│   └── state.tsx         # Context providers for global runtime values
├── tests/                # Automated integration and unit test runners
├── vercel.json           # Vercel deployment specifications and function definitions
├── tsconfig.json         # Strict TypeScript compiler definitions
└── package.json          # Node system requirements and scripts
```

---

## 🚀 Getting Started

### Prerequisites
* **Node.js:** Version 20.x or later installed
* **Package Manager:** `npm` (comes bundled with Node)
* **Vercel CLI:** Installed globally if testing serverless functions locally (`npm i -g vercel`)

### 1. Clone the Repository
```bash
git clone https://github.com
cd CineCritic
```

### 2. Install Dependencies
```bash
npm install
```

### 3. Start Local Development Engine

To run both the **React Frontend** and **Vercel Serverless API Functions** simultaneously, execute:
```bash
npx vercel dev
```
Your local application environment will boot at: **`http://localhost:3000`**

> ⚠️ **Note:** Running `npm run dev` will boot the frontend via Vite, but it **will not** resolve serverless endpoints located inside `/api`. Use `npx vercel dev` for testing live AI workflows.

---

## 🔑 Environment Configuration

Creating an environment file is **entirely optional**. By default, users can fill in their keys directly within the application's browser UI. Use local environment keys if you want your deployed server instance to supply fallback credentials.

Create a `.env` file in your root folder:
```dotenv
# Film Data Catalog Provider
TMDB_API_KEY=your_tmdb_v3_or_v4_token

# AI Processing Provider Keys
ANTHROPIC_API_KEY=your_anthropic_api_key
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_gemini_api_key
MISTRAL_API_KEY=your_mistral_api_key
HF_TOKEN=your_fine_grained_huggingface_token

# Server Fallback Configuration Defaults
AI_PROVIDER=gemini
AI_MODEL=your_preferred_model_id
```

### Environment Variable Layout

| Variable Name | Required | Purpose / Notes |
| :--- | :--- | :--- |
| `TMDB_API_KEY` | Optional | Resolves exact meta-information, matching posters, and filtering metadata. |
| `ANTHROPIC_API_KEY` | Optional | Core API token credential for Anthropic-backed models. |
| `OPENAI_API_KEY` | Optional | Core API token credential for OpenAI-backed models. |
| `GOOGLE_API_KEY` | Optional | Core API token credential for Google Gemini models. |
| `MISTRAL_API_KEY` | Optional | Core API token credential for Mistral analytics models. |
| `HF_TOKEN` | Optional | Token requires explicit `Make calls to Inference Providers` permissions. |
| `AI_PROVIDER` | Optional | Sets the fallback engine. Options: `anthropic`, `openai`, `gemini`, `mistral`, `huggingface`. |
| `AI_MODEL` | Optional | The specific Model ID fallback identifier; required if using Hugging Face server fallback. |

---

## 🔐 Security & API Key Management

* **Storage Location:** Keys stay entirely on your device. They save inside temporary browser memory (`sessionStorage`) by default.
* **Persistent Storage:** Ticking **"Remember keys on this device"** safely shifts them to local persistent storage (`localStorage`).
* **Encryption Notice:** Browser storage layers are unencrypted. Please use restricted, capped API credentials to avoid risk.
* **Transmission Protocol:** Keys are transferred securely via standard HTTPS payloads directly to your endpoint infrastructure. The server loads them down into runtime objects for the request lifecycle, never tracking or writing logs of strings.

---

## ⚡ Pipeline Streaming Schema

Workflows stream event updates utilizing Newline-Delimited JSON (**NDJSON**). Individual event updates conform to the structural layout below:

```json
{
  "executionId": "example-run-id",
  "operation": "critique",
