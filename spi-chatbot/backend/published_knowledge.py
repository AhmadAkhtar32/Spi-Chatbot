"""Publish document knowledge once; load immutable versions for questions."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import rag


KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
APPROVED_SOURCES = (
    Path(__file__).resolve().parent / "approved_demo_sources.json"
)

EXPERTS = ("implementation", "support")
MODULES = {"financial", "inventory", "payroll"}
FORMAT = "spia-published-v1"

FAQ = re.compile(
    r"(?m)^Q:\s*(.+?)\s*\r?\nA:\s*(\S[^\r\n]*)"
)
INCIDENT = re.compile(r"(?m)^INCIDENT TYPE:\s*(.+)$")


class KnowledgeUnavailable(RuntimeError):
    pass


def _filename(value) -> bool:
    return (
        isinstance(value, str)
        and value.endswith(".txt")
        and not any(character in value for character in "/\\:")
        and Path(value).name == value
    )


def _validate_approvals(value) -> dict:
    if not isinstance(value, dict) or set(value) - set(EXPERTS):
        raise ValueError("Invalid expert approval configuration")

    for modules in value.values():
        if not isinstance(modules, dict) or set(modules) - MODULES:
            raise ValueError("Invalid module approval configuration")

        for sources in modules.values():
            if (
                not isinstance(sources, list)
                or not all(map(_filename, sources))
            ):
                raise ValueError("Invalid approved source filename")

    return value


def read_approvals() -> dict:
    try:
        content = APPROVED_SOURCES.read_text(encoding="utf-8")
        return _validate_approvals(json.loads(content))
    except (OSError, ValueError, TypeError) as exc:
        raise KnowledgeUnavailable(
            "Approved document sources are unavailable"
        ) from exc


def approved_sources(expert: str, module: str) -> set[str]:
    return set(
        read_approvals().get(expert, {}).get(module, [])
    )


def _root() -> Path:
    folder_id = hashlib.sha256(
        str(KNOWLEDGE_DIR.resolve()).encode()
    ).hexdigest()[:12]

    return rag._CACHE_ROOT / "published" / folder_id


def _pointer(expert: str) -> dict:
    if expert not in EXPERTS:
        raise KnowledgeUnavailable("Unknown document expert")

    try:
        path = _root() / f"{expert}.current.json"
        pointer = json.loads(path.read_text(encoding="utf-8"))
        digest = pointer["version"]

        if (
            pointer.get("format") != FORMAT
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError("Invalid publication pointer")

        return pointer

    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
    ) as exc:
        raise KnowledgeUnavailable(
            "Document knowledge has not been published successfully"
        ) from exc


def published_version(expert: str) -> str:
    return _pointer(expert)["version"]


@dataclass(frozen=True)
class PublishedKnowledge:
    version: str
    chunks: tuple[dict, ...]
    suggestions: tuple[dict, ...]


@lru_cache(maxsize=4)
def _load_snapshot(
    path: str,
    digest: str,
    expert: str,
    settings_key: str,
) -> PublishedKnowledge:
    try:
        raw = Path(path).read_bytes()

        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Publication checksum does not match")

        data = json.loads(raw)

        if (
            data["format"] != FORMAT
            or data["expert"] != expert
            or data["settings"] != json.loads(settings_key)
        ):
            raise ValueError(
                "Published knowledge needs to be rebuilt"
            )

        approved = _validate_approvals(
            {expert: data["approved"]}
        )[expert]

        chunks = data["chunks"]
        questions = data["suggestions"]

        if (
            not isinstance(chunks, list)
            or not isinstance(questions, list)
        ):
            raise ValueError("Invalid published data")

        for chunk in chunks:
            if (
                not isinstance(chunk, dict)
                or chunk.get("source")
                not in approved.get(chunk.get("module"), [])
                or not isinstance(chunk.get("text"), str)
                or not chunk["text"].strip()
                or not rag._valid_vector(chunk.get("embedding"))
            ):
                raise ValueError("Invalid published section")

        for question in questions:
            if (
                not isinstance(question, dict)
                or question.get("source")
                not in approved.get(question.get("module"), [])
                or question.get("kind") != "document"
                or not isinstance(question.get("question"), str)
                or not 12 <= len(question["question"]) <= 180
            ):
                raise ValueError("Invalid published suggestion")

        return PublishedKnowledge(
            digest,
            tuple(chunks),
            tuple(questions),
        )

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ) as exc:
        raise KnowledgeUnavailable(
            "Published document knowledge is unavailable"
        ) from exc


def get_published(expert: str) -> PublishedKnowledge:
    digest = published_version(expert)
    path = _root() / f"{expert}-{digest}.json"
    settings_key = json.dumps(
        rag._cache_settings(),
        sort_keys=True,
    )

    return _load_snapshot(
        str(path),
        digest,
        expert,
        settings_key,
    )


def _capture(folder: Path) -> tuple[dict[str, bytes], str]:
    if not folder.is_dir():
        raise KnowledgeUnavailable(
            f"Knowledge folder is missing: {folder}"
        )

    files = {
        path.name: path.read_bytes()
        for path in sorted(folder.glob("*.txt"))
    }

    signature = {
        "settings": rag._cache_settings(),
        "documents": {
            name: hashlib.sha256(raw).hexdigest()
            for name, raw in files.items()
        },
    }

    version = hashlib.sha256(
        json.dumps(signature, sort_keys=True).encode()
    ).hexdigest()

    return files, version


def _questions(
    expert: str,
    files: dict,
    approved: dict,
) -> list[dict]:
    candidates = []
    seen = set()

    for source, raw in files.items():
        text = (
            raw.decode("utf-8")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        for document in rag._documents_from_text(source, text):
            module = document["module"]
            body = document["text"]

            if source not in approved.get(module, []):
                continue

            def add(question):
                question = " ".join(question.split())
                key = (module, question.casefold())

                if 12 <= len(question) <= 180 and key not in seen:
                    seen.add(key)
                    candidates.append({
                        "question": question,
                        "source": source,
                        "kind": "document",
                        "module": module,
                    })

            for match in FAQ.finditer(body):
                add(match.group(1))

            if expert == "support" and module == "inventory":
                incidents = list(INCIDENT.finditer(body))

                for index, match in enumerate(incidents):
                    end = (
                        incidents[index + 1].start()
                        if index + 1 < len(incidents)
                        else len(body)
                    )

                    if "Resolution Steps:" in body[match.end():end]:
                        heading = (
                            match.group(1)
                            .strip()
                            .rstrip(".?")
                            .lower()
                        )
                        add(f"How should I resolve {heading}?")

    return candidates


def publish(expert: str) -> dict:
    """Local administrator operation; never called from a chat request."""
    if expert not in EXPERTS:
        raise ValueError("Choose implementation or support")

    all_approvals = read_approvals()

    approved = {
        module: sorted(set(sources))
        for module, sources
        in all_approvals.get(expert, {}).items()
    }

    folder = KNOWLEDGE_DIR / expert
    files, source_version = _capture(folder)

    kb = rag.KnowledgeBase(folder)

    if (
        kb.version != source_version
        or _capture(folder)[1] != source_version
    ):
        raise KnowledgeUnavailable(
            "Documents changed during preparation; publish again"
        )

    if read_approvals() != all_approvals:
        raise KnowledgeUnavailable(
            "Document approvals changed; publish again"
        )

    chunks = [
        chunk
        for chunk in kb.chunks
        if chunk["source"] in approved.get(chunk["module"], [])
    ]

    data = {
        "format": FORMAT,
        "expert": expert,
        "settings": rag._cache_settings(),
        "source_version": source_version,
        "approved": approved,
        "chunks": chunks,
        "suggestions": _questions(expert, files, approved),
    }

    raw = json.dumps(
        data,
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")

    version = hashlib.sha256(raw).hexdigest()

    destination = _root()
    destination.mkdir(parents=True, exist_ok=True)

    snapshot = destination / f"{expert}-{version}.json"

    # Write and validate the complete version before activating it.
    rag._write_cache(snapshot, data)

    _load_snapshot(
        str(snapshot),
        version,
        expert,
        json.dumps(rag._cache_settings(), sort_keys=True),
    )

    rag._write_cache(
        destination / f"{expert}.current.json",
        {
            "format": FORMAT,
            "version": version,
            "published_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "expert": expert,
        "version": version,
        "published_sections": len(chunks),
        "suggestions": len(data["suggestions"]),
        **kb.build_stats,
    }