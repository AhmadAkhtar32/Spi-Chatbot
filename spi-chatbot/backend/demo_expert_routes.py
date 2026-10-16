"""Role- and module-checked document experts for fictional demo users."""

import hashlib
import json
import logging
import os
import re
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from demo_policy import AccessDenied, authorize_expert
from demo_routes import require_demo_identity
from groq_utils import generate_with_retry
from rag import (
    KnowledgeBase,
    build_answer_prompt,
    cosine_similarity,
    embed_texts,
    load_documents,
)


router = APIRouter(
    prefix="/api/demo/experts",
    tags=["Demo experts"],
)

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
APPROVED_SOURCES = (
    Path(__file__).resolve().parent /
    "approved_demo_sources.json"
)

MIN_SCORE = 0.35

FAQ = re.compile(
    r"(?m)^Q:\s*(.+?)\s*\r?\nA:\s*(\S[^\r\n]*)"
)

INCIDENT = re.compile(
    r"(?m)^INCIDENT TYPE:\s*(.+)$"
)


class ExpertQuestion(BaseModel):
    module: Literal["financial", "inventory", "payroll"]
    question: str = Field(min_length=3, max_length=1000)
    source: str | None = None


def _folder_fingerprint(folder: Path) -> str:
    """Change the knowledge-base cache when documents change."""
    digest = hashlib.sha256()

    for path in sorted(folder.glob("*.txt")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())

    return digest.hexdigest()


@lru_cache(maxsize=4)
def _knowledge_base_for_version(
    name: str,
    version: str,
) -> KnowledgeBase:
    return KnowledgeBase(KNOWLEDGE_DIR / name)


def _knowledge_base(name: str) -> KnowledgeBase:
    folder = KNOWLEDGE_DIR / name

    return _knowledge_base_for_version(
        name,
        _folder_fingerprint(folder),
    )


def _approved_sources(name: str, module: str) -> set[str]:
    """Only reviewed files may be searched or suggested."""
    try:
        manifest = json.loads(
            APPROVED_SOURCES.read_text(encoding="utf-8")
        )

        files = manifest.get(name, {}).get(module, [])

        if not isinstance(files, list) or any(
            not isinstance(item, str)
            or Path(item).name != item
            or not item.endswith(".txt")
            for item in files
        ):
            raise ValueError("Invalid source manifest")

        return set(files)

    except (OSError, ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=503,
            detail="Approved sources are not configured",
        ) from None


def _require_expert(
    identity: tuple[dict, str],
    name: str,
    module: str,
) -> None:
    user, surface = identity

    try:
        authorize_expert(
            user,
            surface,
            f"{name}_expert",
            module,
        )
    except AccessDenied:
        raise HTTPException(
            status_code=403,
            detail="Expert or module is not licensed",
        ) from None


def _document_questions(
    name: str,
    module: str,
    approved: set[str],
) -> list[dict]:
    """Find questions supported by currently approved documents."""
    candidates: list[dict] = []
    seen: set[str] = set()

    documents = load_documents(KNOWLEDGE_DIR / name)

    for doc in documents:
        if (
            doc["module"] != module
            or doc["source"] not in approved
        ):
            continue

        source = doc["source"]
        body = doc["text"]

        def add(question: str) -> None:
            question = " ".join(question.split())
            key = question.casefold()

            if (
                12 <= len(question) <= 180
                and key not in seen
            ):
                seen.add(key)

                candidates.append({
                    "question": question,
                    "source": source,
                    "kind": "document",
                })

        # Include a document FAQ only when it has an adjacent answer.
        for match in FAQ.finditer(body):
            if match.group(2).strip():
                add(match.group(1).strip())

        # Inventory incidents also contain documented resolution steps.
        # Derive an action question from each current incident heading.
        if name == "support" and module == "inventory":
            incidents = list(INCIDENT.finditer(body))

            for index, match in enumerate(incidents):
                end = (
                    incidents[index + 1].start()
                    if index + 1 < len(incidents)
                    else len(body)
                )

                section = body[match.end():end]

                if "Resolution Steps:" in section:
                    heading = (
                        match.group(1)
                        .strip()
                        .rstrip(".?")
                    )

                    add(
                        "How should I resolve "
                        f"{heading.lower()}?"
                    )

    return candidates


@router.get("/suggestions")
def expert_suggestions(
    response: Response,
    expert: Literal[
        "support_expert",
        "implementation_expert",
    ],
    module: Literal[
        "financial",
        "inventory",
        "payroll",
    ],
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    """Return up to six questions for this verified user."""
    response.headers["Cache-Control"] = "no-store"

    name = expert.removesuffix("_expert")

    _require_expert(identity, name, module)

    approved = _approved_sources(name, module)

    candidates = _document_questions(
        name,
        module,
        approved,
    )

    count = min(6, len(candidates))

    return {
        "suggestions": secrets.SystemRandom().sample(
            candidates,
            count,
        ),
        "available": len(candidates),
    }


def _answer(
    name: str,
    request: ExpertQuestion,
    identity: tuple[dict, str],
) -> dict:
    _require_expert(
        identity,
        name,
        request.module,
    )

    approved = _approved_sources(
        name,
        request.module,
    )

    if (
        request.source is not None
        and request.source not in approved
    ):
        raise HTTPException(
            status_code=403,
            detail="Reference source is not approved",
        )

    question = request.question.strip()

    if len(question) < 3:
        raise HTTPException(
            status_code=400,
            detail="Enter a longer question",
        )

    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured",
        )

    try:
        kb = _knowledge_base(name)

        # Both the module and the source must be approved before
        # any document text is sent to the AI provider.
        allowed = [
            chunk
            for chunk in kb.chunks
            if chunk.get("module") == request.module
            and chunk.get("source") in approved
            and (
                request.source is None
                or chunk.get("source") == request.source
            )
        ]

        if not allowed:
            return {
                "reply": (
                    "No approved reference material "
                    "for this module."
                ),
                "sources": [],
            }

        vector = embed_texts([question])[0]

        ranked = sorted(
            allowed,
            key=lambda chunk: cosine_similarity(
                vector,
                chunk["embedding"],
            ),
            reverse=True,
        )[:5]

        if cosine_similarity(
            vector,
            ranked[0]["embedding"],
        ) < MIN_SCORE:
            return {
                "reply": (
                    "I could not find this in the "
                    "approved reference material."
                ),
                "sources": [],
            }

        prompt = build_answer_prompt(
            "SPI " + name.capitalize() + " Expert",
            question,
            ranked,
        )

        from groq import Groq

        result = generate_with_retry(
            Groq(api_key=api_key),
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        return {
            "reply": (
                result.choices[0].message.content
                or ""
            ),
            "sources": sorted({
                chunk["source"]
                for chunk in ranked
            }),
        }

    except Exception:
        logging.exception(
            "Demo %s expert failed",
            name,
        )

        raise HTTPException(
            status_code=502,
            detail="Expert service is unavailable",
        ) from None


@router.post("/implementation")
def implementation_expert(
    request: ExpertQuestion,
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    return _answer(
        "implementation",
        request,
        identity,
    )


@router.post("/support")
def support_expert(
    request: ExpertQuestion,
    identity: tuple[dict, str] = Depends(
        require_demo_identity
    ),
):
    return _answer(
        "support",
        request,
        identity,
    )