"""
Small resilience layer around Groq calls — mirrors gemini_utils.py.
"""

import time
import logging

logger = logging.getLogger("groq_utils")


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "503" in msg or "rate limit" in msg or "overloaded" in msg or "capacity" in msg


def generate_with_retry(client, max_retries: int = 3, **kwargs):
    """client.chat.completions.create(**kwargs), retried on rate-limit/overload errors."""
    delay = 2
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.warning("chat.completions.create failed (attempt %d/%d): %s", attempt + 1, max_retries, exc)
            if not _is_transient(exc) or attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay *= 2


def friendly_error_message(exc: Exception) -> str:
    logger.error("Groq call failed: %s", exc)
    msg = str(exc).lower()
    if "429" in msg or "rate limit" in msg:
        return "The AI service is busy right now (rate limit reached). Please wait a moment and try again."
    if "503" in msg or "overloaded" in msg or "capacity" in msg:
        return "The AI service is temporarily overloaded. Please try again in a few seconds."
    return "Something went wrong talking to the AI service. Please try again."