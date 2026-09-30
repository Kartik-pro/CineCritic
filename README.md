<div align="center">

# 🎬 CineCritic

**An AI movie critic with a cinema soul — punchy 50-word reviews and smart recommendations, powered by Mistral or Gemini.**

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-ff4b4b)
![LangChain](https://img.shields.io/badge/LLM-LangChain-1c3c3c)
![License](https://img.shields.io/badge/license-MIT-green)

</div>

---

## ✨ Features

- 🎞️ **Instant reviews** — type any movie and get a ticket-style review in **4–5 bullet points, max 50 words total**.
- 🍿 **Smart recommendations** — describe a movie you loved, a mood, or a genre and get poster-style picks with a one-line reason each.
- 🔁 **One-click flow** — hit *Review this →* on any recommendation to jump straight to its review.
- 🔑 **Built-in API key manager** — paste your key in the sidebar and it is saved to `.env` automatically.
- 🔌 **Multi-provider** — switch between **Mistral** and **Gemini** (and set any model name) without touching code.
- 🎨 **Cinema theme** — dark glassmorphism UI, gold film-strip branding, ticket and poster cards.

## 🖼️ Screenshots

> Add screenshots here after your first run, e.g. `docs/review.png` and `docs/recommend.png`.

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/<your-username>/CineCritic.git
cd CineCritic

# 2. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
streamlit run app.py
```

Then open the sidebar, choose a provider, paste your API key and click **💾 Save to .env**. That's it.

### API keys

| Provider | Environment variable | Where to get a key |
|----------|---------------------|--------------------|
| Mistral  | `MISTRAL_API_KEY`   | [console.mistral.ai](https://console.mistral.ai) |
| Gemini   | `GOOGLE_API_KEY`    | [aistudio.google.com](https://aistudio.google.com) |

You can also copy `.env.example` to `.env` and fill it in by hand.

> 🔒 `.env` is listed in `.gitignore`. Never commit your keys.

## 🗂️ Project Structure

```
CineCritic/
├── app.py                     # Streamlit entry point
├── requirements.txt
├── .env.example               # Template for API keys
├── cinecritic/
│   ├── config.py              # Paths, MAX_WORDS, supported providers
│   ├── env_manager.py         # Load / save API keys in .env
│   ├── llm.py                 # init_chat_model wrapper with caching
│   ├── prompt_template.py     # Your critic system prompt (Cine_prompt)
│   ├── prompts.py             # Review + recommendation prompt templates
│   ├── schemas.py             # Pydantic models for structured output
│   ├── services.py            # Review / recommendation logic (UI-independent)
│   └── ui/
│       ├── style.css          # Cinema theme
│       ├── styles.py          # CSS injector
│       ├── components.py      # HTML for hero, ticket and movie cards
│       ├── sidebar.py         # Provider, model and API key panel
│       ├── pages.py           # Review and Recommend pages
│       └── state.py           # Session state and navigation
```

## ⚙️ How It Works

1. **Review:** `prompts.py` sends your critic persona plus strict output rules to the model. `services.to_bullets()` then hard-caps the answer at `MAX_WORDS`, so the limit holds even if the model overshoots.
2. **Recommend:** the model's reply is forced into a Pydantic schema (`Recommendations`) using `with_structured_output`, so cards render from clean objects instead of parsed text.
3. **Providers:** `llm.py` uses LangChain's `init_chat_model("<provider>:<model>")`, so switching providers only changes a string.

## 🛠️ Customization

| I want to... | Change |
|--------------|--------|
| Change the review length | `MAX_WORDS` in `cinecritic/config.py` |
| Change the critic's personality | `Cine_prompt` in `cinecritic/prompt_template.py` |
| Add another provider (e.g. OpenAI) | Add a `Provider(...)` entry in `config.py` and `pip install` its LangChain package |
| Restyle the app | Edit `cinecritic/ui/style.css` |

## 🩹 Troubleshooting

- **`TypeError: expected str, got list`** — use `ChatPromptTemplate.from_messages([...])` for a list of messages; `from_template` only accepts a string. (This repo already does it correctly.)
- **Missing-variable error from the prompt** — literal `{ }` in a prompt string are read as variables. Here the system prompt is sent as a `SystemMessage`, so braces are safe.
- **`ModuleNotFoundError`** — activate your virtual environment and re-run `pip install -r requirements.txt`.
- **Model not found** — model names change often; check your provider's docs and update the *Model* field in the sidebar.

## 🗺️ Roadmap

- [ ] Real posters, ratings and trailers via the TMDB API
- [ ] Watchlist saved between sessions
- [ ] Streaming (typewriter) reviews
- [ ] Filters for language, decade and "already seen"
- [ ] Docker image and one-click deploy

## 🤝 Contributing

Issues and pull requests are welcome. Fork the repo, create a feature branch, and open a PR with a short description of your change.

## 📄 License

Released under the [MIT License](LICENSE).
