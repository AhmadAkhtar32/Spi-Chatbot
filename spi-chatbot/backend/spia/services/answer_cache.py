"""Bounded, per-process cache for approved document answers only."""

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass


TTL_SECONDS = 30 * 60
MAX_ENTRIES = 256
MAX_REPLY_CHARACTERS = 16000


def enabled() -> bool:
    return os.environ.get(
        "ENABLE_DOCUMENT_ANSWER_CACHE", "1"
    ) == "1"


def make_key(**context) -> str:
    encoded = json.dumps(
        context,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class _Entry:
    created: float
    reply: str
    sources: tuple[str, ...]


class DocumentAnswerCache:
    def __init__(
        self,
        ttl=TTL_SECONDS,
        max_entries=MAX_ENTRIES,
        clock=time.monotonic,
    ):
        if ttl <= 0 or max_entries < 1:
            raise ValueError("Cache limits must be positive")

        self.ttl = ttl
        self.max_entries = max_entries
        self.clock = clock
        self._entries = OrderedDict()
        self._lock = threading.Lock()

    def clear(self):
        with self._lock:
            self._entries.clear()

    def get(self, key):
        if not enabled():
            return None

        with self._lock:
            entry = self._entries.pop(key, None)

            if (
                entry is None
                or self.clock() - entry.created >= self.ttl
            ):
                return None

            self._entries[key] = entry

            return {
                "reply": entry.reply,
                "sources": list(entry.sources),
            }

    def put(self, key, reply, sources) -> bool:
        if (
            not enabled()
            or not isinstance(reply, str)
            or not reply.strip()
            or len(reply) > MAX_REPLY_CHARACTERS
            or not isinstance(sources, list)
            or not 1 <= len(sources) <= 5
            or any(
                not isinstance(source, str) or not source
                for source in sources
            )
        ):
            return False

        with self._lock:
            now = self.clock()

            expired = [
                name
                for name, entry in self._entries.items()
                if now - entry.created >= self.ttl
            ]

            for name in expired:
                del self._entries[name]

            self._entries.pop(key, None)

            self._entries[key] = _Entry(
                now,
                reply,
                tuple(sources),
            )

            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

        return True


document_answers = DocumentAnswerCache()