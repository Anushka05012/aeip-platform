"""
Central configuration for the llm-services module.

Loads settings from environment variables (via a local .env file in dev,
or real environment variables in CI/deploy). Keeping this in one place
means the Groq client, chunker defaults, and any future embedding worker
(Sept 11 task) all read from the same source of truth.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env if present. In production (Render/Vercel/CI) real env vars
# are already set, so this is a no-op there.
load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer, got: {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    groq_model: str
    chunk_max_tokens: int
    chunk_overlap_tokens: int

    @staticmethod
    def load(require_api_key: bool = True) -> "Settings":
        api_key = os.getenv("GROQ_API_KEY", "")
        if require_api_key and not api_key:
            raise ConfigError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key "
                "from https://console.groq.com/keys"
            )

        return Settings(
            groq_api_key=api_key,
            groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            chunk_max_tokens=_get_int("CHUNK_MAX_TOKENS", 500),
            chunk_overlap_tokens=_get_int("CHUNK_OVERLAP_TOKENS", 50),
        )
