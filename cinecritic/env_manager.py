"""Read and persist API keys in the project's .env file."""
from __future__ import annotations

import os

from dotenv import load_dotenv, set_key

from .config import ENV_PATH


def load_env() -> None:
    load_dotenv(ENV_PATH)


def get_api_key(env_var: str) -> str:
    return os.getenv(env_var, "")


def save_api_key(env_var: str, value: str) -> None:
    """Write the key to .env and make it available to the running process."""
    ENV_PATH.touch(exist_ok=True)
    set_key(str(ENV_PATH), env_var, value.strip())
    os.environ[env_var] = value.strip()
