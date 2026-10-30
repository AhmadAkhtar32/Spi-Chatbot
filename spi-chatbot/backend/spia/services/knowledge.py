"""Publish document knowledge once; load immutable versions for questions."""

from spia.core.paths import BACKEND_DIR

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from spia.services import retrieval as rag

KNOWLEDGE_DIR = BACKEND_DIR / "knowledge"
APPROVED_SOURCES = BACKEND_DIR / "data/approved_sources.json"
EXPERTS = ("implementation", "support")
MODULES = {"financial", "inventory", "payroll"}
FORMAT = "spia-published-v1"
FAQ = re.compile(r"(?m)^Q:\s*(.+?)\s*\r?\nA:\s*(\S[^\r\n]*)")
INCIDENT = re.compile(r"(?m)^INCIDENT TYPE:\s*(.+)$")


class KnowledgeUnavailable(RuntimeError):
    pass


def _filename(value) -> bool:
    return (
        isinstance(value, str) and value.endswith(".txt")
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
            if not isinstance(sources, list) or not all(map(_filename, sources)):
                raise ValueError("Invalid approved source filename")
    return value


def read_approvals() -> dict:
    try:
        return _validate_approvals(
            json.loads(APPROVED_SOURCES.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, TypeError) as exc:
        raise KnowledgeUnavailable(
            "Approved document sources are unavailable"
        ) from exc


def approved_sources(expert: str, module: str) -> set[str]:
    return set(read_approvals().get(expert, {}).get(module, []))


def _root() -> Path:
    configured = os.environ.get("SPIA_PUBLISHED_DIR")
    if configured is not None:
        if not configured.strip():
            raise KnowledgeUnavailable("SPIA_PUBLISHED_DIR must not be empty")
        destination = Path(configured.strip()).expanduser()
        if not destination.is_absolute():
            destination = BACKEND_DIR / destination
        return destination.resolve()

    folder_id = hashlib.sha256(
        str(KNOWLEDGE_DIR.resolve()).encode()
    ).hexdigest()[:12]
    return rag._CACHE_ROOT / "published" / folder_id


def _pointer(expert: str) -> dict:
    if expert not in EXPERTS:
        raise KnowledgeUnavailable("Unknown document expert")
    try:
        pointer = json.loads(
            (_root() / f"{expert}.current.json").read_text(encoding="utf-8")
        )
        digest = pointer["version"]
        if (
            pointer.get("format") != FORMAT
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError("Invalid publication pointer")
        return pointer
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
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
    path: str, digest: str, expert: str, settings_key: str
) -> PublishedKnowledge:
    try:
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Publication checksum does not match")
        data = json.loads(raw)
        if (
            data["format"] != FORMAT or data["expert"] != expert
            or data["settings"] != json.loads(settings_key)
        ):
            raise ValueError("Published knowledge needs to be rebuilt")
        approved = _validate_approvals({expert: data["approved"]})[expert]
        chunks, questions = data["chunks"], data["suggestions"]
        if not isinstance(chunks, list) or not isinstance(questions, list):
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

        return PublishedKnowledge(digest, tuple(chunks), tuple(questions))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise KnowledgeUnavailable(
            "Published document knowledge is unavailable"
        ) from exc


def get_published(expert: str) -> PublishedKnowledge:
    digest = published_version(expert)
    path = _root() / f"{expert}-{digest}.json"
    settings_key = json.dumps(rag._cache_settings(), sort_keys=True)
    return _load_snapshot(str(path), digest, expert, settings_key)


def _capture(folder: Path) -> tuple[dict[str, bytes], str]:
    if not folder.is_dir():
        raise KnowledgeUnavailable(f"Knowledge folder is missing: {folder}")
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


def _questions(expert: str, files: dict, approved: dict) -> list[dict]:
    candidates, seen = [], set()
    for source, raw in files.items():
        text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        for document in rag._documents_from_text(source, text):
            module, body = document["module"], document["text"]
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
                        heading = match.group(1).strip().rstrip(".?").lower()
                        add(f"How should I resolve {heading}?")
    return candidates


def publish(expert: str) -> dict:
    """Local administrator operation; never called from a chat request."""
    if expert not in EXPERTS:
        raise ValueError("Choose implementation or support")
    all_approvals = read_approvals()
    approved = {
        module: sorted(set(sources))
        for module, sources in all_approvals.get(expert, {}).items()
    }
    folder = KNOWLEDGE_DIR / expert
    files, source_version = _capture(folder)
    kb = rag.KnowledgeBase(folder)
    if kb.version != source_version or _capture(folder)[1] != source_version:
        raise KnowledgeUnavailable(
            "Documents changed during preparation; publish again"
        )
    if read_approvals() != all_approvals:
        raise KnowledgeUnavailable(
            "Document approvals changed; publish again"
        )
    chunks = [
        chunk for chunk in kb.chunks
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
        data, ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    version = hashlib.sha256(raw).hexdigest()
    destination = _root()
    destination.mkdir(parents=True, exist_ok=True)
    snapshot = destination / f"{expert}-{version}.json"

    rag._write_cache(snapshot, data)
    _load_snapshot(
        str(snapshot),
        version,
        expert,
        json.dumps(rag._cache_settings(), sort_keys=True),
    )
    rag._write_cache(destination / f"{expert}.current.json", {
        "format": FORMAT,
        "version": version,
        "published_at": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "expert": expert,
        "version": version,
        "published_sections": len(chunks),
        "suggestions": len(data["suggestions"]),
        **kb.build_stats,
    }


# Company knowledge uploads
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def _upload_root():
    selected = os.environ.get("SPIA_SECURITY_DIR")

    if not selected or not Path(selected).is_absolute():
        raise KnowledgeUnavailable(
            "Private upload storage is unavailable"
        )

    return Path(selected) / "knowledge_uploads"


def _upload_name(source):
    if (
        not isinstance(source, str)
        or not 1 <= len(source) <= 120
        or not source.lower().endswith(".txt")
        or any(c in source for c in "/\\:\x00\r\n")
        or Path(source).name != source
    ):
        raise ValueError("Provide a plain TXT filename")


def save_pending_upload(identity, source, raw, confirm):
    import shutil
    import tempfile
    import uuid

    _upload_name(source)

    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError(
            "Upload must contain at most 2 MiB of TXT data"
        )

    text = raw.decode("utf-8-sig")

    if not text.strip() or "\x00" in text:
        raise ValueError(
            "Provide a nonempty UTF-8 text file"
        )

    stored = text.encode("utf-8")
    root = _upload_root()
    root.mkdir(parents=True, exist_ok=True)

    document_id = uuid.uuid4().hex
    destination = root / document_id

    temporary = Path(
        tempfile.mkdtemp(
            prefix=".staging-",
            dir=root,
        )
    )

    receipt = {
        "schema_version": 1,
        "id": document_id,
        "source": source,
        "company_id": identity.company_id,
        "installation_id": identity.installation_id,
        "owner_id": identity.user_id,
        "status": "pending_review",
        "content_sha256": hashlib.sha256(stored).hexdigest(),
        "size_bytes": len(stored),
    }

    committed = False

    try:
        (temporary / "content.txt").write_bytes(stored)

        (temporary / "receipt.json").write_text(
            json.dumps(receipt),
            encoding="utf-8",
        )

        confirm()
        temporary.rename(destination)
        committed = True
        confirm()

    except Exception:
        if committed:
            shutil.rmtree(destination)
        raise

    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    return {
        key: receipt[key]
        for key in ("id", "source", "status")
    }


def list_upload_receipts(identity):
    root = _upload_root()
    result = []

    if not root.exists():
        return {"documents": result}

    for folder in sorted(root.iterdir()):
        if re.fullmatch(
            r"[0-9a-f]{32}", folder.name
        ) is None:
            continue

        try:
            with (folder / "receipt.json").open("rb") as file:
                raw = file.read(8193)

            if len(raw) > 8192:
                raise ValueError("Invalid upload receipt")

            receipt = json.loads(raw.decode("utf-8"))

            if (
                receipt["company_id"],
                receipt["installation_id"],
                receipt["owner_id"],
            ) != (
                identity.company_id,
                identity.installation_id,
                identity.user_id,
            ):
                continue

            _upload_name(receipt["source"])

            if (
                receipt["schema_version"] != 1
                or receipt["id"] != folder.name
                or receipt["status"] not in {
                    "pending_review",
                    "approved",
                    "blocked",
                }
            ):
                raise ValueError("Invalid upload receipt")

            result.append({
                key: receipt[key]
                for key in ("id", "source", "status")
            })

        except (OSError, ValueError, KeyError, TypeError):
            raise KnowledgeUnavailable(
                "Upload receipts unavailable"
            ) from None

    return {"documents": result}



# Local upload review
def _reviewed_upload(document_id):
    from spia.security.store import read_configuration

    if re.fullmatch(r"[0-9a-f]{32}", document_id) is None:
        raise ValueError("Invalid document ID")

    settings, _, _, _ = read_configuration()
    folder = _upload_root() / document_id

    with (folder / "receipt.json").open("rb") as file:
        receipt_bytes = file.read(8193)

    with (folder / "content.txt").open("rb") as file:
        content = file.read(MAX_UPLOAD_BYTES + 1)

    if (
        len(receipt_bytes) > 8192
        or not 0 < len(content) <= MAX_UPLOAD_BYTES
    ):
        raise ValueError("Invalid stored upload size")

    def unique(pairs):
        result = {}

        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate receipt key")
            result[key] = value

        return result

    receipt = json.loads(
        receipt_bytes.decode("utf-8"),
        object_pairs_hook=unique,
    )

    if (
        receipt["company_id"],
        receipt["installation_id"],
        receipt["id"],
    ) != (
        settings.company_id,
        settings.installation_id,
        document_id,
    ):
        raise ValueError("Upload installation mismatch")

    _upload_name(receipt["source"])

    if (
        receipt["schema_version"] != 1
        or receipt["status"] not in {
            "pending_review", "approved", "blocked",
        }
    ):
        raise ValueError("Invalid upload receipt")

    if (
        receipt["content_sha256"]
        != hashlib.sha256(content).hexdigest()
        or receipt["size_bytes"] != len(content)
    ):
        raise ValueError(
            "Stored content changed; approval refused"
        )

    text = content.decode("utf-8")

    if not text.strip() or "\x00" in text:
        raise ValueError("Invalid stored text")

    token = hashlib.sha256(
        receipt_bytes + b"\x00" + content
    ).hexdigest()

    return folder, receipt_bytes, receipt, text, token


def inspect_uploaded_document(document_id):
    _, _, receipt, text, token = _reviewed_upload(
        document_id
    )

    return {
        "document": receipt,
        "text": text,
        "review_token": token,
    }


def review_uploaded_document(
    document_id,
    review_token,
    decision,
    classifications,
):
    import getpass
    import tempfile

    if decision not in {"approve", "block"}:
        raise ValueError("Choose approve or block")

    classes = sorted(set(classifications))

    if any(
        not isinstance(value, str)
        or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}",
            value,
        ) is None
        for value in classes
    ):
        raise ValueError("Invalid classification")

    if decision == "approve" and not classes:
        raise ValueError(
            "Approval requires explicit classifications"
        )

    if len(classes) > 16:
        raise ValueError("Too many classifications")

    if re.fullmatch(
        r"[0-9a-f]{64}", review_token
    ) is None:
        raise ValueError(
            "Use the review token from inspection"
        )

    if re.fullmatch(
        r"[0-9a-f]{32}", document_id
    ) is None:
        raise ValueError("Invalid document ID")

    folder = _upload_root() / document_id
    lock = folder / ".review.lock"

    descriptor = os.open(
        lock,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )

    temporary = None

    try:
        os.close(descriptor)

        _, previous, receipt, _, actual_token = (
            _reviewed_upload(document_id)
        )

        if actual_token != review_token:
            raise ValueError(
                "Document or receipt changed; inspect it again"
            )

        if (
            decision == "approve"
            and receipt["status"] != "pending_review"
        ):
            raise ValueError(
                "Only pending uploads can be approved"
            )

        receipt.update(
            status=(
                "approved"
                if decision == "approve"
                else "blocked"
            ),
            classifications=(
                classes
                if decision == "approve"
                else receipt.get("classifications", [])
            ),
            reviewed_by=getpass.getuser(),
            reviewed_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

        history = folder / (
            "review-before-" + actual_token + ".json"
        )

        if history.exists():
            if history.read_bytes() != previous:
                raise ValueError("Review history mismatch")
        else:
            with history.open("xb") as file:
                file.write(previous)

        raw = json.dumps(
            receipt, indent=2
        ).encode("utf-8")

        if len(raw) > 8192:
            raise ValueError(
                "Review receipt is too large"
            )

        with tempfile.NamedTemporaryFile(
            dir=folder,
            delete=False,
        ) as file:
            temporary = Path(file.name)
            file.write(raw)

        if (
            _reviewed_upload(document_id)[4]
            != actual_token
        ):
            raise ValueError(
                "Document changed during review; inspect it again"
            )

        os.replace(
            temporary,
            folder / "receipt.json",
        )

    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

        lock.unlink(missing_ok=True)

    return {
        key: receipt[key]
        for key in (
            "id", "source", "status", "classifications",
        )
    }



# Approved upload indexing
def prepare_uploaded_document(document_id):
    if re.fullmatch(r"[0-9a-f]{32}", document_id) is None:
        raise ValueError("Invalid document ID")

    folder = _upload_root() / document_id
    lock = folder / ".review.lock"

    descriptor = os.open(
        lock,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )

    try:
        os.close(descriptor)

        _, _, receipt, text, token = (
            _reviewed_upload(document_id)
        )

        classes = receipt.get("classifications")

        if (
            receipt["status"] != "approved"
            or not isinstance(classes, list)
            or not classes
            or any(
                not isinstance(value, str)
                or re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}",
                    value,
                ) is None
                for value in classes
            )
        ):
            raise ValueError(
                "Only approved, classified uploads "
                "can be prepared"
            )

        context = {
            "format": "spia-upload-index-v1",
            "document_id": document_id,
            "review_token": token,
            "settings": rag._cache_settings(),
        }

        texts = rag.chunk_text(text)
        source = document_id + ".txt"
        target = folder / "index.json"
        chunks = None

        try:
            with target.open("rb") as file:
                raw = file.read(
                    128 * 1024 * 1024 + 1
                )

            if len(raw) > 128 * 1024 * 1024:
                raise ValueError(
                    "Invalid cached index size"
                )

            saved = json.loads(raw)
            candidate = saved.get("chunks")

            if (
                {
                    key: saved.get(key)
                    for key in context
                } == context
                and isinstance(candidate, list)
                and len(candidate) == len(texts)
                and all(
                    isinstance(chunk, dict)
                    and chunk.get("text") == texts[index]
                    and chunk.get("source") == source
                    and chunk.get("module") == "project"
                    and rag._valid_vector(
                        chunk.get("embedding")
                    )
                    for index, chunk in enumerate(candidate)
                )
            ):
                chunks = candidate

        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
        ):
            pass

        reused = chunks is not None

        if not reused:
            vectors = rag.embed_texts(texts)

            if (
                len(vectors) != len(texts)
                or not all(
                    map(rag._valid_vector, vectors)
                )
            ):
                raise ValueError(
                    "Embedding generation failed"
                )

            chunks = [
                {
                    "source": source,
                    "module": "project",
                    "text": body,
                    "embedding": vector,
                }
                for body, vector in zip(texts, vectors)
            ]

        if _reviewed_upload(document_id)[4] != token:
            raise ValueError(
                "Upload changed during preparation"
            )

        if not reused:
            rag._write_cache(
                target,
                {
                    **context,
                    "chunks": chunks,
                },
            )

        if _reviewed_upload(document_id)[4] != token:
            raise ValueError(
                "Upload changed during preparation"
            )

        return {
            "document_id": document_id,
            "status": "prepared",
            "sections": len(chunks),
            "reused": reused,
        }

    finally:
        lock.unlink(missing_ok=True)
