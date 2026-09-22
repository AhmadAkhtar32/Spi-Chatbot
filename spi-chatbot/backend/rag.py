"""
RAG (Retrieval-Augmented Generation) engine.
----------------------------------------------
This is the shared engine behind Implementation Expert and Support Expert
(and, later, Project Knowledge Expert). Each one is just this same
pipeline pointed at a different folder of documents.

How it works, in order:
  1. load_documents  — read every .txt file in a folder
  2. chunk_text      — split each document into smaller overlapping pieces
  3. embed           — turn each chunk into a vector (via Gemini's
                        embedding model) that represents its meaning
  4. search          — embed the user's question the same way, then find
                        the chunks whose vectors are numerically closest
                        (cosine similarity) to the question's vector
  5. build_answer_prompt — hand only those relevant chunks to Gemini, and
                        ask it to answer using just that material

Embeddings are cached to disk (see _cache_path below), not just in
memory. This matters in practice: uvicorn's --reload restarts the whole
Python process on every file save, which would otherwise force every
document to be re-embedded from scratch on every restart — burning
through the free tier's embed_content rate limit (100 requests/minute)
very quickly during active development. The cache is keyed by a hash of
the folder's contents, so editing a document automatically invalidates
it and triggers a fresh (one-time) re-embed.
"""

import hashlib
import json
import math
from pathlib import Path
from gemini_utils import embed_with_retry


def load_documents(folder: Path) -> list[dict]:
    """Read every .txt file in a folder into {source, text} dicts."""
    docs = []
    if not folder.exists():
        return docs
    for path in sorted(folder.glob("*.txt")):
        docs.append({"source": path.name, "text": path.read_text(encoding="utf-8")})
    return docs


def chunk_text(text: str, chunk_size: int = 180, overlap: int = 30) -> list[str]:
    """
    Split text into overlapping word-count chunks. Overlap prevents a
    relevant sentence from being awkwardly cut in half between two chunks.
    Sizes are in words, not characters — small enough to keep each chunk
    focused on one topic, per document.
    """
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap
    return chunks


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """How numerically 'close' two embedding vectors are — 1.0 = identical
    meaning, 0 = unrelated. This is the actual 'search' in vector search."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _folder_hash(folder: Path) -> str:
    """Fingerprint of a knowledge folder's contents — changes if any file
    is added, removed, or edited, so the cache below auto-invalidates."""
    h = hashlib.sha256()
    for path in sorted(folder.glob("*.txt")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


class KnowledgeBase:
    """One embedded, searchable set of documents (e.g. all Implementation
    Expert reference guides). Built once, then reused across requests —
    and cached to disk so it survives server restarts too."""

    EMBED_MODEL = "gemini-embedding-001"
    BATCH_SIZE = 90  # texts per embed_content call — stays under typical API batch caps

    def __init__(self, folder: Path, client):
        self.client = client
        self.chunks: list[dict] = []  # [{source, text, embedding}]
        self._build(folder)

    def _cache_path(self, folder: Path) -> Path:
        cache_dir = folder.parent / ".cache"
        cache_dir.mkdir(exist_ok=True)
        safe_name = folder.name.replace("/", "_")
        return cache_dir / f"{safe_name}.json"

    def _build(self, folder: Path):
        from google.genai.types import EmbedContentConfig

        current_hash = _folder_hash(folder)
        cache_file = self._cache_path(folder)

        # Reuse cached embeddings if this folder's contents haven't changed
        # since they were last computed — skips the API entirely.
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                if cached.get("hash") == current_hash:
                    self.chunks = cached["chunks"]
                    return
            except (json.JSONDecodeError, KeyError):
                pass  # corrupt/old cache format — fall through and rebuild

        docs = load_documents(folder)
        all_chunks = []
        for doc in docs:
            for chunk in chunk_text(doc["text"]):
                all_chunks.append({"text": chunk, "source": doc["source"]})

        if not all_chunks:
            self.chunks = []
            return

        texts = [c["text"] for c in all_chunks]
        embeddings = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            result = embed_with_retry(
                self.client,
                model=self.EMBED_MODEL,
                contents=batch,
                config=EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
            )
            embeddings.extend(result.embeddings)

        for chunk, embedding in zip(all_chunks, embeddings):
            chunk["embedding"] = embedding.values

        self.chunks = all_chunks
        try:
            cache_file.write_text(
                json.dumps({"hash": current_hash, "chunks": all_chunks}), encoding="utf-8"
            )
        except OSError:
            # Read-only filesystem (e.g. Vercel serverless) — the embeddings
            # still work for this request, they just won't persist to disk.
            pass

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Return the top_k chunks most relevant to the query."""
        from google.genai.types import EmbedContentConfig

        if not self.chunks:
            return []

        result = embed_with_retry(
            self.client,
            model=self.EMBED_MODEL,
            contents=query,
            config=EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        query_vector = result.embeddings[0].values

        scored = [
            (cosine_similarity(query_vector, chunk["embedding"]), chunk)
            for chunk in self.chunks
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]


def build_answer_prompt(expert_name: str, question: str, chunks: list[dict]) -> str:
    """Assemble the final prompt: relevant chunks + instructions + question."""
    if not chunks:
        context_block = "(No relevant reference material was found.)"
    else:
        context_block = "\n\n".join(
            f"[Source: {c['source']}]\n{c['text']}" for c in chunks
        )

    return f"""You are the {expert_name} for SPI, D-Biz Solutions' ERP system.

Answer the question using ONLY the reference material below. If the
material doesn't cover the question, say so honestly instead of guessing
or using outside knowledge. Where relevant, mention which document the
information came from.

Reference material:
---
{context_block}
---

Question: {question}
"""