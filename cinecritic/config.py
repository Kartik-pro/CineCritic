"""Central configuration: paths, limits and supported LLM providers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"

# Hard cap for the whole review, across all bullet points.
MAX_WORDS = 50


@dataclass(frozen=True)
class Provider:
    label: str          # shown in the UI
    prefix: str         # LangChain init_chat_model provider prefix
    env_var: str        # environment variable holding the API key
    default_model: str


PROVIDERS: dict[str, Provider] = {
    "Mistral": Provider("Mistral", "mistralai", "MISTRAL_API_KEY", "mistral-large-latest"),
    "Gemini": Provider("Gemini", "google_genai", "GOOGLE_API_KEY", "gemini-3.5-flash"),
}
