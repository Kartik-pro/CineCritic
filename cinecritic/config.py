"""Central configuration: paths, limits, cache settings, providers, tasks and scoring."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APP_VERSION = "3.0.0"
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"

# In-session workspace limits (no database: data lives in st.session_state + JSON backup files)
MAX_ARCHIVE = 2000
MAX_USAGE_EVENTS = 5000
MAX_RUNS = 200
MAX_BACKUP_BYTES = 5_000_000

# Hard cap for the quick-take review, across all bullet points.
MAX_WORDS = 50

# Bump whenever prompts or schemas change so stale cached/stored analyses are never reused.
PROMPT_VERSION = "4"

# Request handling
REQUEST_TIMEOUT_S = 90
MAX_RETRIES = 2  # retained for reference; retries are handled centrally in pipeline.py
MAX_QUERY_CHARS = 120

# Caches (in-process, never contain API keys)
ANALYSIS_CACHE_TTL_S = 6 * 60 * 60
ANALYSIS_CACHE_MAX = 128
META_CACHE_TTL_S = 24 * 60 * 60
META_CACHE_MAX = 512
LISTING_CACHE_TTL_S = 30 * 60        # discovery / search listings

NUM_SIMILAR = 4
TMDB_ENV_VAR = "TMDB_API_KEY"



# --------------------------------------------------------------------------- providers
@dataclass(frozen=True)
class Provider:
    label: str          # shown in the UI
    prefix: str         # LangChain init_chat_model provider prefix
    env_var: str        # secret / environment variable name (also the st.secrets key)
    default_model: str  # a starting point only; always editable, never assumed to be available
    package: str = ""   # python module that must be importable for this provider
    pip_name: str = ""
    docs_url: str = ""
    key_hint: str = ""


PROVIDERS: dict[str, Provider] = {
    "Gemini": Provider("Gemini", "google_genai", "GOOGLE_API_KEY", "gemini-3.5-flash",
                       "langchain_google_genai", "langchain-google-genai",
                       "https://aistudio.google.com/apikey", "Google AI Studio key"),
    "OpenAI": Provider("OpenAI", "openai", "OPENAI_API_KEY", "gpt-4o-mini",
                       "langchain_openai", "langchain-openai",
                       "https://platform.openai.com/api-keys", "Starts with sk-"),
    "Anthropic": Provider("Anthropic", "anthropic", "ANTHROPIC_API_KEY", "claude-sonnet-5-5",
                          "langchain_anthropic", "langchain-anthropic",
                          "https://console.anthropic.com/settings/keys", "Starts with sk-ant-"),
    "Mistral": Provider("Mistral", "mistralai", "MISTRAL_API_KEY", "mistral-large-latest",
                        "langchain_mistralai", "langchain-mistralai",
                        "https://console.mistral.ai/api-keys", "Mistral console key"),
}

# --------------------------------------------------------------------------- AI tasks
@dataclass(frozen=True)
class Task:
    id: str
    label: str
    help: str
    structured: bool       # needs structured (schema) output
    default_temperature: float | None = None


TASKS: dict[str, Task] = {
    "analysis": Task("analysis", "Deep Film Analysis", "Full structured critique with eight craft scores.", True),
    "quick": Task("quick", "Quick Critique", "Fast 50-word review (no scorecards).", False),
    "recommend": Task("recommend", "Recommendations", "Similar films and taste-based picks.", True),
    "search_assist": Task("search_assist", "Search Assistance", "Recall a title from a vague description.", True),
    "summarize": Task("summarize", "Summarization", "Comparison write-ups and summaries.", False),
    "extract": Task("extract", "Structured Metadata Extraction",
                    "Turn a natural-language request into search filters.", True),
    "ask": Task("ask", "Ask the Critic", "Conversational film assistant.", False),
}

# Per-task generation limits that are always safe to apply
SAFE_TIMEOUT_RANGE = (10, 180)
SAFE_MAX_TOKENS_RANGE = (64, 16000)

# --------------------------------------------------------------------------- scoring
# (schema field, card title, short label). Strengths & Flaws and the verdict are separate.
DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("plot", "Plot & Premise"),
    ("screenplay", "Story & Screenplay"),
    ("direction", "Direction & Vision"),
    ("acting", "Acting & Performances"),
    ("cinematography", "Cinematography & Visuals"),
    ("music", "Music & Sound Design"),
    ("pacing", "Editing & Pacing"),
    ("themes", "Emotional Impact & Themes"),
)
SHORT_LABELS = {
    "plot": "Plot", "screenplay": "Screenplay", "direction": "Direction", "acting": "Acting",
    "cinematography": "Cinematography", "music": "Sound & Music", "pacing": "Editing",
    "themes": "Themes",
}
DEFAULT_WEIGHTS = {key: 1.0 for key, _ in DIMENSIONS}
SCORE_SCALES = (10, 5, 100)           # selectable display scales; stored scores are always 0-10
MAX_WEIGHT = 5.0

EXAMPLE_FILMS: tuple[str, ...] = (
    "Oppenheimer (2023)",
    "Dune: Part Two",
    "Interstellar",
    "Parasite",
    "Past Lives",
)

SPOILER_LEVELS = ("none", "light", "full")
LANGUAGES = ("English", "Hindi", "Spanish", "French", "German", "Japanese", "Portuguese", "Italian")
