"""
RAG (Retrieval-Augmented Generation) engine.
----------------------------------------------
This is the shared engine behind Implementation Expert and Support Expert
(and, later, Project Knowledge Expert). Each one is just this same
pipeline pointed at a different folder of documents.

How it works, in order:
  1. load_documents  — read every .txt file in a folder, and tag each
                        chunk with which module it belongs to
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

Module tagging (financial / inventory / payroll / general) is used by
app.py's licensing check, so a question can be distinguished as either
"not licensed for this module" or "licensed, but not covered." Most
files are homogeneous enough that their filename alone tells you their
module (see infer_module). Two files mix content from more than one
module within a single file — for those, tagging happens per incident/
section instead of per file, using that section's own "Category:" line
or "INCIDENT TYPE:" heading (see MIXED_CONTENT_FILES / _module_for_block)
rather than guessing.

Embeddings are cached to disk (see _cache_path below), keyed by a hash
of the folder's contents AND a schema version — so changing what a
chunk stores (like adding "module", or changing how modules are tagged)
automatically invalidates old caches without needing to manually delete
them.
"""

import hashlib
import json
import math
import re
from pathlib import Path

_embedder = None

# Bump this whenever the shape of a cached chunk changes (new fields,
# different module logic, etc.) so old caches auto-invalidate instead
# of silently loading stale/incompatible data.
SCHEMA_VERSION = "v3-per-block-module"

# Files known to mix content from more than one module within a single
# file — for these, module tagging happens per incident/section using
# that section's own "Category:" line or "INCIDENT TYPE:" heading,
# instead of one module tag for the whole file. Every other file's
# content is homogeneous enough that filename-based tagging already
# matches its content correctly.
MIXED_CONTENT_FILES = {
    "incident_log_examples.txt": "incident_number",
    "payroll_and_access_incidents.txt": "incident_type",
}


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
    """Filename-based module tag for a whole file. Used for every file
    except the ones in MIXED_CONTENT_FILES, whose content mixes modules
    and is tagged per-section instead (see _module_for_block)."""
    name = source.lower()
    if name.startswith("gl_"):
        return "financial"
    if "inventory" in name:
        return "inventory"
    if "payroll" in name:
        return "payroll"
    return "general"


def _blocks_for_mixed_file(filename: str, full_text: str) -> list[str]:
    """Split a mixed-content file into its individual incidents/sections,
    each of which gets tagged separately."""
    split_kind = MIXED_CONTENT_FILES[filename]
    if split_kind == "incident_number":
        pattern = re.compile(r'(?=^Incident #\d+)', re.MULTILINE)
    else:
        pattern = re.compile(r'(?=^INCIDENT TYPE:)', re.MULTILINE)
    return [b for b in pattern.split(full_text) if b.strip()]


def _module_for_block(block: str) -> str:
    """Module for one incident/section, read from the block's own
    'Category:' line if present, else its own heading line — both are
    text the document itself states, not an inference."""
    lowered = block.lower()
    category_match = re.search(r'category:\s*(.+)', lowered)
    signal_text = category_match.group(1) if category_match else lowered.split('\n', 1)[0]
    if "payroll" in signal_text:
        return "payroll"
    if "inventory" in signal_text:
        return "inventory"
    return "general"


def load_documents(folder: Path) -> list[dict]:
    """Read every .txt file in a folder into {source, text, module}
    dicts. See MIXED_CONTENT_FILES for the two files that get split at
    incident/section boundaries and tagged individually rather than as
    one file."""
    docs = []
    if not folder.exists():
        return docs
    for path in sorted(folder.glob("*.txt")):
        full_text = path.read_text(encoding="utf-8")

        if path.name in MIXED_CONTENT_FILES:
            for block in _blocks_for_mixed_file(path.name, full_text):
                docs.append({"source": path.name, "text": block, "module": _module_for_block(block)})
        else:
            docs.append({"source": path.name, "text": full_text, "module": infer_module(path.name)})
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
            for chunk in chunk_text(doc["text"]):
                all_chunks.append({"text": chunk, "source": doc["source"], "module": doc["module"]})

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