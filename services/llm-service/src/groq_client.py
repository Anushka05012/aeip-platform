"""
Thin wrapper around the official `groq` Python SDK.

Why a wrapper instead of calling the SDK directly everywhere:
- one place to configure retries/timeouts for flaky network conditions
- one place to swap models (e.g. a faster model for chunk-level tagging,
  a bigger model for the CI/CD failure RCA pipeline that Neeraj builds on
  top of this later)
- easy to mock in tests without touching the real API
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional, TypedDict

from groq import Groq
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import Settings

logger = logging.getLogger(__name__)


class ChatMessage(TypedDict):
    role: str  # "system" | "user" | "assistant"
    content: str


class GroqClient:
    """Small convenience wrapper around groq.Groq for chat completions."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings.load()
        self._client = Groq(api_key=self.settings.groq_api_key)

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type(Exception),
    )
    def chat(
        self,
        messages: Iterable[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs,
    ) -> str:
        """
        Send a chat completion request and return the text of the first
        response. Retries with exponential backoff on transient errors
        (rate limits, timeouts, 5xx).
        """
        response = self._client.chat.completions.create(
            model=model or self.settings.groq_model,
            messages=list(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return response.choices[0].message.content

    def ping(self) -> bool:
        """
        Quick connectivity/credentials check. Returns True if Groq
        responds successfully to a trivial prompt, False otherwise.
        Useful for a health-check endpoint or a one-off smoke test.
        """
        try:
            reply = self.chat(
                [{"role": "user", "content": "Reply with exactly: pong"}],
                max_tokens=5,
                temperature=0,
            )
            return "pong" in reply.lower()
        except Exception:
            logger.exception("Groq ping failed")
            return False
