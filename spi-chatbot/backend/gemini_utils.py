import time
import logging

logger = logging.getLogger("gemini_utils")


def _is_transient(exc: Exception) -> bool:
    msg = str(exc)
    return "429" in msg or "503" in msg or "RESOURCE_EXHAUSTED" in msg or "UNAVAILABLE" in msg


def generate_with_retry(client, max_retries: int = 3, **kwargs):
    """client.models.generate_content(**kwargs), retried on 429/503."""
    delay = 2
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(**kwargs)
        except Exception as exc:
            logger.warning("generate_content failed (attempt %d/%d): %s", attempt + 1, max_retries, exc)
            if not _is_transient(exc) or attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay *= 2


def embed_with_retry(client, max_retries: int = 3, **kwargs):
    """client.models.embed_content(**kwargs), retried on 429/503."""
    delay = 2
    for attempt in range(max_retries):
        try:
            return client.models.embed_content(**kwargs)
        except Exception as exc:
            logger.warning("embed_content failed (attempt %d/%d): %s", attempt + 1, max_retries, exc)
            if not _is_transient(exc) or attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay *= 2


def friendly_error_message(exc: Exception) -> str:
    """User-facing message — never leak raw API error payloads."""
    logger.error("Gemini call failed: %s", exc)
    msg = str(exc)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "The AI service is busy right now (rate limit reached). Please wait a moment and try again."
    if "503" in msg or "UNAVAILABLE" in msg:
        return "The AI service is temporarily overloaded. Please try again in a few seconds."
    return "Something went wrong talking to the AI service. Please try again."