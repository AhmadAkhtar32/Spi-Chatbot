"""
RAG (Retrieval-Augmented Generation) engine.
----------------------------------------------
This is the shared engine behind Implementation Expert and Support Expert
(and, later, Project Knowledge Expert). Each one is just this same
pipeline pointed at a different folder of documents.

How it works, in order:
  1. load_documents  — read every .txt file in a folder
  2. chunk_text      — split each document into smaller overlapping pieces
  3. embed           — turn each chunk into a vector using a local
                        embedding model (fastembed / ONNX runtime) — no
                        external API, no rate limit, and small enough to
                        deploy on Vercel's serverless Python functions
  4. search          — embed the user's question the same way, then find
                        the chunks whose vectors are numerically closest
                        (cosine similarity) to the question's vector, each
                        tagged with its source module and similarity score
  5. build_answer_prompt — hand only the relevant chunks to Groq, and ask
                        it to answer using just that material

Each chunk is tagged with a "module" (financial / inventory / payroll /
general) via infer_module() below — a filename-based placeholder used
until a real documentation-defined module map replaces it. This lets
app.py distinguish "you're not licensed for this module" from "you're
licensed, but this isn't in our documents" instead of collapsing both
into one not-authorized message.

Embeddings are cached to disk (see _cache_path below), keyed by a hash
of the folder's contents AND a schema version — so changing what a
chunk stores (like adding "module") automatically invalidates old
caches without needing to manually delete them.
"""

import hashlib
import json
import math
from pathlib import Path

_embedder = None

# Bump this whenever the shape of a cached chunk changes (new fields,
# different module logic, etc.) so old caches auto-invalidate instead
# of silently loading stale/incompatible data.
SCHEMA_VERSION = "v2-module-tagged"


def _get_embedder():
    """Loads the local embedding model once, lazily. Uses fastembed
    (ONNX Runtime) instead of sentence-transformers/torch — this keeps
    the deployed bundle small enough to fit Vercel's Python function
    size limit, while still needing no external embedding API."""
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        # /tmp is the only writable path in Vercel's serverless runtime,
        # so the model cache is pointed there explicitly rather than
        # relying on a default location that may not be writable.
        _embedder = TextEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            cache_dir="/tmp/fastembed_cache",
        )
    return _embedder


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Turn a list of strings into embedding vectors, entirely locally."""
    embedder = _get_embedder()
    vectors = list(embedder.embed(texts))
    return [v.tolist() for v in vectors]


def infer_module(source: str) -> str:
    """Best-effort module tag for a document, based on its filename.

    PLACEHOLDER: this is a filename heuristic, not an authoritative
    mapping. It exists so licensing can be checked at the module level
    (e.g. 'financial' vs 'inventory' vs 'payroll') even though the
    knowledge folders aren't physically split by module yet. Replace
    this once a real documentation-defined module map is provided.
    """
    name = source.lower()
    if name.startswith("gl_"):
        return "financial"
    if "inventory" in name:
        return "inventory"
    if "payroll" in name:
        return "payroll"
    # Cross-cutting content (login issues, performance, general
    # troubleshooting) doesn't belong to one module — always allowed.
    return "general"


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
    """Fingerprint of a knowledge folder's contents plus the current
    schema version — changes if any file is added/removed/edited, OR
    if the cached chunk format itself has changed, so the cache below
    auto-invalidates in either case."""
    h = hashlib.sha256()
    h.update(SCHEMA_VERSION.encode())
    for path in sorted(folder.glob("*.txt")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


class KnowledgeBase:
    """One embedded, searchable set of documents (e.g. all Implementation
    Expert reference guides). Built once, then reused across requests —
    and cached to disk so it survives server restarts too."""

    def __init__(self, folder: Path):
        self.chunks: list[dict] = []  # [{source, text, module, embedding}]
        self._build(folder)

    def _cache_path(self, folder: Path) -> Path:
        cache_dir = folder.parent / ".cache"
        cache_dir.mkdir(exist_ok=True)
        safe_name = folder.name.replace("/", "_")
        return cache_dir / f"{safe_name}.json"

    def _build(self, folder: Path):
        current_hash = _folder_hash(folder)
        cache_file = self._cache_path(folder)

        # Reuse cached embeddings if this folder's contents and the
        # schema haven't changed since they were last computed.
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
            module = infer_module(doc["source"])
            for chunk in chunk_text(doc["text"]):
                all_chunks.append({"text": chunk, "source": doc["source"], "module": module})

        if not all_chunks:
            self.chunks = []
            return

        texts = [c["text"] for c in all_chunks]
        vectors = embed_texts(texts)

        for chunk, vector in zip(all_chunks, vectors):
            chunk["embedding"] = vector

        self.chunks = all_chunks
        try:
            cache_file.write_text(
                json.dumps({"hash": current_hash, "chunks": all_chunks}), encoding="utf-8"
            )
        except OSError:
            # Read-only filesystem (e.g. Vercel serverless) — the
            # embeddings still work for this request, they just won't
            # persist to disk.
            pass

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Return the top_k chunks most relevant to the query, each
        carrying its source, module, and similarity score — the caller
        uses 'module' for licensing and 'score' to detect off-topic
        questions instead of trusting the model to word that itself."""
        if not self.chunks:
            return []

        query_vector = embed_texts([query])[0]

        scored = [
            (cosine_similarity(query_vector, chunk["embedding"]), chunk)
            for chunk in self.chunks
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)

        results = []
        for score, chunk in scored[:top_k]:
            enriched = dict(chunk)
            enriched["score"] = score
            results.append(enriched)
        return results


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