"""Document retrieval with incremental, persistent embedding caches.

This module prepares TXT documents. It does not cache business records
or generated answers. Publishing and answer caching are separate steps.
"""

import hashlib
import json
import logging
import math
import os
import re
import tempfile
import threading
from pathlib import Path

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384
CHUNK_SIZE = 180
CHUNK_OVERLAP = 30
SCHEMA_VERSION = "v4-per-document-module"

_embedder = None
_embedder_lock = threading.Lock()
_build_lock = threading.RLock()
logger = logging.getLogger(__name__)


def _writable_cache_root() -> Path:
    configured = os.environ.get("SPIA_CACHE_DIR")
    preferred = (
        Path(configured).expanduser()
        if configured
        else Path(__file__).resolve().parent / "knowledge" / ".cache"
    )
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=preferred):
            pass
        return preferred
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "spia_ai_assistant"
        fallback.mkdir(parents=True, exist_ok=True)
        logger.warning("Using temporary document cache: %s", fallback)
        return fallback


_CACHE_ROOT = _writable_cache_root()
os.environ.setdefault("HF_HOME", str(_CACHE_ROOT / "huggingface"))
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE_ROOT / "xdg"))

MIXED_CONTENT_FILES = {
    "incident_log_examples.txt": "incident_number",
    "payroll_and_access_incidents.txt": "incident_type",
}


def _get_embedder():
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                from fastembed import TextEmbedding

                model_cache = _CACHE_ROOT / "models"
                model_cache.mkdir(parents=True, exist_ok=True)
                _embedder = TextEmbedding(
                    model_name=EMBEDDING_MODEL,
                    cache_dir=str(model_cache),
                )
    return _embedder


def embed_texts(texts: list[str]) -> list[list[float]]:
    return [vector.tolist() for vector in _get_embedder().embed(texts)]


def infer_module(source: str) -> str:
    name = source.lower()
    if name.startswith("gl_"):
        return "financial"
    if "inventory" in name:
        return "inventory"
    if "payroll" in name:
        return "payroll"
    return "general"


def _blocks_for_mixed_file(filename: str, full_text: str) -> list[str]:
    pattern = (
        r"(?=^Incident #\d+)"
        if MIXED_CONTENT_FILES[filename] == "incident_number"
        else r"(?=^INCIDENT TYPE:)"
    )
    return [
        block for block in re.split(pattern, full_text, flags=re.MULTILINE)
        if block.strip()
    ]


def _module_for_block(block: str) -> str:
    lowered = block.lower()
    category = re.search(r"category:\s*(.+)", lowered)
    signal = category.group(1) if category else lowered.split("\n", 1)[0]
    if "payroll" in signal:
        return "payroll"
    if "inventory" in signal:
        return "inventory"
    return "general"


def _documents_from_text(source: str, text: str) -> list[dict]:
    if source in MIXED_CONTENT_FILES:
        return [
            {"source": source, "text": block, "module": _module_for_block(block)}
            for block in _blocks_for_mixed_file(source, text)
        ]
    return [{"source": source, "text": text, "module": infer_module(source)}]


def load_documents(folder: Path) -> list[dict]:
    documents = []
    for path in sorted(Path(folder).glob("*.txt")):
        documents.extend(
            _documents_from_text(path.name, path.read_text(encoding="utf-8"))
        )
    return documents


def chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    if chunk_size <= 0 or not 0 <= overlap < chunk_size:
        raise ValueError("Require chunk_size > 0 and 0 <= overlap < chunk_size")
    words = text.split()
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
    if len(a) != len(b):
        raise ValueError("Embedding dimensions do not match")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _cache_settings() -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIMENSIONS,
        "chunk_size": CHUNK_SIZE,
        "overlap": CHUNK_OVERLAP,
    }


def _valid_vector(vector) -> bool:
    return (
        isinstance(vector, list)
        and len(vector) == EMBEDDING_DIMENSIONS
        and all(
            type(value) in (int, float) and math.isfinite(value)
            for value in vector
        )
        and any(value != 0 for value in vector)
    )


def _reusable(entry, digest: str, source: str, has_text: bool) -> bool:
    if not isinstance(entry, dict) or entry.get("digest") != digest:
        return False
    chunks = entry.get("chunks")
    if not isinstance(chunks, list) or bool(chunks) != has_text:
        return False
    return all(
        isinstance(chunk, dict)
        and chunk.get("source") == source
        and isinstance(chunk.get("text"), str)
        and bool(chunk["text"].strip())
        and chunk.get("module") in {"financial", "inventory", "payroll", "general"}
        and _valid_vector(chunk.get("embedding"))
        for chunk in chunks
    )


def _read_cache(path: Path, settings: dict) -> dict:
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if (
        not isinstance(cached, dict)
        or cached.get("settings") != settings
        or not isinstance(cached.get("documents"), dict)
    ):
        return {}
    return cached


def _write_cache(path: Path, data: dict) -> None:
    """Replace a complete file; never leave a partially written JSON cache."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class KnowledgeBase:
    """Prepare current TXT contents, reusing each unchanged document's vectors."""

    def __init__(self, folder: Path):
        self.chunks: list[dict] = []
        self.version = ""
        self.build_stats: dict = {}
        with _build_lock:
            self._build(Path(folder))

    def _cache_path(self, folder: Path) -> Path:
        folder_id = hashlib.sha256(str(folder.resolve()).encode()).hexdigest()[:12]
        return _CACHE_ROOT / f"{folder.name}-{folder_id}.json"

    def _build(self, folder: Path):
        settings = _cache_settings()
        cache_file = self._cache_path(folder)
        cached = _read_cache(cache_file, settings)
        previous = cached.get("documents", {})
        documents = {}
        pending = []
        reused = 0
        rebuilt = 0

        for path in sorted(folder.glob("*.txt")):
            raw = path.read_bytes()
            text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
            digest = hashlib.sha256(raw).hexdigest()
            entry = previous.get(path.name)
            if _reusable(entry, digest, path.name, bool(text.strip())):
                documents[path.name] = entry
                reused += 1
                continue

            chunks = []
            for document in _documents_from_text(path.name, text):
                for section in chunk_text(document["text"], CHUNK_SIZE, CHUNK_OVERLAP):
                    chunks.append({
                        "text": section,
                        "source": path.name,
                        "module": document["module"],
                    })
            documents[path.name] = {"digest": digest, "chunks": chunks}
            pending.extend(chunks)
            rebuilt += 1

        if pending:
            vectors = embed_texts([chunk["text"] for chunk in pending])
            if len(vectors) != len(pending) or not all(map(_valid_vector, vectors)):
                raise ValueError("Embedding model returned invalid vectors")
            for chunk, vector in zip(pending, vectors):
                chunk["embedding"] = vector

        removed = len(set(previous) - set(documents))
        signature = {
            "settings": settings,
            "documents": {name: value["digest"] for name, value in documents.items()},
        }
        self.version = hashlib.sha256(
            json.dumps(signature, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self.chunks = [
            chunk for document in documents.values() for chunk in document["chunks"]
        ]

        saved = True
        if not cached or rebuilt or removed or cached.get("version") != self.version:
            try:
                _write_cache(cache_file, {
                    "settings": settings,
                    "version": self.version,
                    "documents": documents,
                })
            except OSError:
                saved = False
                logger.warning("Document cache could not be saved: %s", cache_file)

        self.build_stats = {
            "reused_documents": reused,
            "rebuilt_documents": rebuilt,
            "removed_documents": removed,
            "embedded_chunks": len(pending),
            "total_chunks": len(self.chunks),
            "cache_saved": saved,
        }

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.chunks or top_k <= 0:
            return []
        vector = embed_texts([query])[0]
        if not _valid_vector(vector):
            raise ValueError("Embedding model returned an invalid question vector")
        scored = sorted(
            ((cosine_similarity(vector, chunk["embedding"]), chunk) for chunk in self.chunks),
            key=lambda pair: pair[0], reverse=True,
        )
        return [dict(chunk, score=score) for score, chunk in scored[:top_k]]


def build_answer_prompt(expert_name: str, question: str, chunks: list[dict]) -> str:
    context = "\n\n".join(
        f"[Source: {chunk['source']}]\n{chunk['text']}" for chunk in chunks
    ) or "(No relevant reference material was found.)"
    return f"""You are the {expert_name} for SPI, D-Biz Solutions' ERP system.

Answer the question using ONLY the reference material below. If the
material doesn't cover the question, say so honestly instead of guessing
or using outside knowledge. Where relevant, mention which document the
information came from.

Reference material:
---
{context}
---

Question: {question}
"""