"""
Document search for the Implementation and Support experts.
Documents are split into chunks, embedded locally, and searched by similarity.
"""

import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path

_embedder = None


def _writable_cache_root() -> Path:
    """Use persistent local storage when writable, otherwise runtime temp storage."""
    configured = os.environ.get("SPIA_CACHE_DIR")
    preferred = (
        Path(configured).expanduser()
        if configured
        else Path(__file__).resolve().parent / "knowledge" / ".cache"
    )
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        # An existing directory might still be read-only.
        with tempfile.TemporaryFile(dir=preferred):
            pass
        return preferred
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "spia_ai_assistant"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


_CACHE_ROOT = _writable_cache_root()

# Hugging Face reads these settings when its library is imported.
os.environ.setdefault("HF_HOME", str(_CACHE_ROOT / "huggingface"))
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE_ROOT / "xdg"))

SCHEMA_VERSION = "v3-per-block-module"

MIXED_CONTENT_FILES = {
    "incident_log_examples.txt": "incident_number",
    "payroll_and_access_incidents.txt": "incident_type",
}


def _get_embedder():
    """Load the local embedding model once per running server instance."""
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding

        model_cache = _CACHE_ROOT / "models"
        model_cache.mkdir(parents=True, exist_ok=True)
        _embedder = TextEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            cache_dir=str(model_cache),
        )
    return _embedder


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Turn text into vectors using the local model."""
    embedder = _get_embedder()
    vectors = list(embedder.embed(texts))
    return [vector.tolist() for vector in vectors]


def infer_module(source: str) -> str:
    """Determine the module for a document from its filename."""
    name = source.lower()
    if name.startswith("gl_"):
        return "financial"
    if "inventory" in name:
        return "inventory"
    if "payroll" in name:
        return "payroll"
    return "general"


def _blocks_for_mixed_file(filename: str, full_text: str) -> list[str]:
    """Split a file containing incidents from different modules."""
    split_kind = MIXED_CONTENT_FILES[filename]
    if split_kind == "incident_number":
        pattern = re.compile(r"(?=^Incident #\d+)", re.MULTILINE)
    else:
        pattern = re.compile(r"(?=^INCIDENT TYPE:)", re.MULTILINE)
    return [block for block in pattern.split(full_text) if block.strip()]


def _module_for_block(block: str) -> str:
    """Read an incident's module from its category or heading."""
    lowered = block.lower()
    category_match = re.search(r"category:\s*(.+)", lowered)
    signal_text = (
        category_match.group(1)
        if category_match
        else lowered.split("\n", 1)[0]
    )
    if "payroll" in signal_text:
        return "payroll"
    if "inventory" in signal_text:
        return "inventory"
    return "general"


def load_documents(folder: Path) -> list[dict]:
    """Read the text documents and attach their module labels."""
    docs = []
    if not folder.exists():
        return docs

    for path in sorted(folder.glob("*.txt")):
        full_text = path.read_text(encoding="utf-8")

        if path.name in MIXED_CONTENT_FILES:
            for block in _blocks_for_mixed_file(path.name, full_text):
                docs.append({
                    "source": path.name,
                    "text": block,
                    "module": _module_for_block(block),
                })
        else:
            docs.append({
                "source": path.name,
                "text": full_text,
                "module": infer_module(path.name),
            })
    return docs


def chunk_text(
    text: str,
    chunk_size: int = 180,
    overlap: int = 30,
) -> list[str]:
    """Split a document into overlapping word groups."""
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
    """Measure how close two vectors are."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _folder_hash(folder: Path) -> str:
    """Change the cache key when documents or the cache format change."""
    digest = hashlib.sha256()
    digest.update(SCHEMA_VERSION.encode())
    for path in sorted(folder.glob("*.txt")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class KnowledgeBase:
    """A searchable collection of document chunks."""

    def __init__(self, folder: Path):
        self.chunks: list[dict] = []
        self._build(folder)

    def _cache_path(self, folder: Path) -> Path:
        safe_name = folder.name.replace("/", "_")
        folder_id = hashlib.sha256(
            str(folder.resolve()).encode()
        ).hexdigest()[:12]
        return _CACHE_ROOT / f"{safe_name}-{folder_id}.json"

    def _build(self, folder: Path):
        current_hash = _folder_hash(folder)
        cache_file = self._cache_path(folder)

        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                if cached.get("hash") == current_hash:
                    self.chunks = cached["chunks"]
                    return
            except (json.JSONDecodeError, KeyError):
                pass

        docs = load_documents(folder)
        all_chunks = []
        for doc in docs:
            for chunk in chunk_text(doc["text"]):
                all_chunks.append({
                    "text": chunk,
                    "source": doc["source"],
                    "module": doc["module"],
                })

        if not all_chunks:
            self.chunks = []
            return

        vectors = embed_texts([chunk["text"] for chunk in all_chunks])
        for chunk, vector in zip(all_chunks, vectors):
            chunk["embedding"] = vector

        self.chunks = all_chunks
        try:
            cache_file.write_text(
                json.dumps({"hash": current_hash, "chunks": all_chunks}),
                encoding="utf-8",
            )
        except OSError:
            # Search still works if a temporary cache cannot be saved.
            pass

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Find the document chunks most relevant to a question."""
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


def build_answer_prompt(
    expert_name: str,
    question: str,
    chunks: list[dict],
) -> str:
    """Give the AI the relevant document text and the user's question."""
    if not chunks:
        context_block = "(No relevant reference material was found.)"
    else:
        context_block = "\n\n".join(
            f"[Source: {chunk['source']}]\n{chunk['text']}"
            for chunk in chunks
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