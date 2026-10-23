"""Licensed document experts using explicitly published knowledge."""

import logging
import os
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

import published_knowledge
from demo_policy import AccessDenied, authorize_expert
from demo_routes import require_demo_identity
from document_answer_cache import document_answers, make_key
from groq_utils import generate_with_retry
from published_knowledge import (
    KnowledgeUnavailable,
    approved_sources,
    get_published,
    published_version,
)
from rag import (
    _valid_vector,
    build_answer_prompt,
    cosine_similarity,
    embed_texts,
)


router = APIRouter(
    prefix="/api/demo/experts",
    tags=["Demo experts"],
)

MIN_SCORE = 0.35
CHAT_MODEL = "openai/gpt-oss-120b"

# Change this revision when the document prompt or answer rules change.
ANSWER_RULES_VERSION = "published-doc-answer-v1"


class ExpertQuestion(BaseModel):
    module: Literal["financial", "inventory", "payroll"]
    question: str = Field(min_length=3, max_length=1000)
    source: str | None = Field(default=None, max_length=255)


def _fail(status: int, detail: str):
    raise HTTPException(
        status_code=status,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


def _require_expert(identity, name: str, module: str):
    user, surface = identity

    try:
        authorize_expert(
            user,
            surface,
            f"{name}_expert",
            module,
        )
    except AccessDenied:
        _fail(403, "Expert or module is not licensed")


def _knowledge(name: str, module: str):
    try:
        return (
            get_published(name),
            approved_sources(name, module),
        )
    except KnowledgeUnavailable:
        logging.exception(
            "Published %s knowledge is unavailable",
            name,
        )
        _fail(503, "Document knowledge is currently unavailable")


def _confirm_current(
    name,
    module,
    identity,
    version,
    sources,
):
    _require_expert(identity, name, module)

    try:
        if not set(sources).issubset(
            approved_sources(name, module)
        ):
            _fail(
                403,
                "Reference access changed; please ask again",
            )

        if published_version(name) != version:
            _fail(
                409,
                "Reference material changed; please ask again",
            )

    except KnowledgeUnavailable:
        _fail(503, "Document knowledge is currently unavailable")


@router.get("/suggestions")
def expert_suggestions(
    response: Response,
    expert: Literal[
        "support_expert",
        "implementation_expert",
    ],
    module: Literal["financial", "inventory", "payroll"],
    identity=Depends(require_demo_identity),
):
    response.headers["Cache-Control"] = "no-store"

    name = expert.removesuffix("_expert")
    _require_expert(identity, name, module)

    knowledge, approved = _knowledge(name, module)

    candidates = [
        {
            "question": item["question"],
            "source": item["source"],
            "kind": item["kind"],
        }
        for item in knowledge.suggestions
        if (
            item["module"] == module
            and item["source"] in approved
        )
    ]

    selected = secrets.SystemRandom().sample(
        candidates,
        min(6, len(candidates)),
    )

    _confirm_current(
        name,
        module,
        identity,
        knowledge.version,
        [item["source"] for item in selected],
    )

    return {
        "suggestions": selected,
        "available": len(candidates),
        "knowledge_version": knowledge.version,
    }


def _answer(
    name: str,
    request: ExpertQuestion,
    identity,
    response: Response,
) -> dict:
    response.headers["X-Document-Answer-Cache"] = "bypass"

    _require_expert(identity, name, request.module)

    question = request.question.strip()

    if len(question) < 3:
        _fail(400, "Enter a longer question")

    knowledge, approved = _knowledge(name, request.module)

    if (
        request.source is not None
        and request.source not in approved
    ):
        _fail(403, "Reference source is not approved")

    allowed = [
        chunk
        for chunk in knowledge.chunks
        if (
            chunk["module"] == request.module
            and chunk["source"] in approved
            and (
                request.source is None
                or chunk["source"] == request.source
            )
        )
    ]

    if not allowed:
        return {
            "reply": "No approved reference material for this module.",
            "sources": [],
            "knowledge_version": knowledge.version,
        }

    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        _fail(503, "AI service is not configured")

    user, surface = identity

    cache_key = make_key(
        installation=str(
            published_knowledge.KNOWLEDGE_DIR.resolve()
        ),
        user=user,
        surface=surface,
        expert=name,
        module=request.module,
        source=request.source,
        question=question,
        knowledge_version=knowledge.version,
        approved=sorted(approved),
        model=CHAT_MODEL,
        rules=ANSWER_RULES_VERSION,
        minimum_score=MIN_SCORE,
        top_k=5,
    )

    cached = document_answers.get(cache_key)

    if cached is not None:
        _confirm_current(
            name,
            request.module,
            identity,
            knowledge.version,
            cached["sources"],
        )

        response.headers["X-Document-Answer-Cache"] = "hit"

        return {
            **cached,
            "knowledge_version": knowledge.version,
        }

    try:
        vector = embed_texts([question])[0]

        if not _valid_vector(vector):
            raise ValueError("Invalid question vector")

        ranked = sorted(
            allowed,
            key=lambda chunk: cosine_similarity(
                vector,
                chunk["embedding"],
            ),
            reverse=True,
        )[:5]

        if (
            cosine_similarity(
                vector,
                ranked[0]["embedding"],
            )
            < MIN_SCORE
        ):
            return {
                "reply": (
                    "I could not find this in the "
                    "approved reference material."
                ),
                "sources": [],
                "knowledge_version": knowledge.version,
            }

        prompt = build_answer_prompt(
            "SPI " + name.capitalize() + " Expert",
            question,
            ranked,
        )

        from groq import Groq

        result = generate_with_retry(
            Groq(api_key=api_key),
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        reply = result.choices[0].message.content or ""

    except Exception:
        logging.exception("Demo %s expert failed", name)
        _fail(502, "Expert service is unavailable")

    sources = sorted({
        chunk["source"]
        for chunk in ranked
    })

    _confirm_current(
        name,
        request.module,
        identity,
        knowledge.version,
        sources,
    )

    if getattr(result.choices[0], "finish_reason", None) == "stop":
        if document_answers.put(cache_key, reply, sources):
            response.headers["X-Document-Answer-Cache"] = "miss"

    return {
        "reply": reply,
        "sources": sources,
        "knowledge_version": knowledge.version,
    }


@router.post("/implementation")
def implementation_expert(
    request: ExpertQuestion,
    response: Response,
    identity=Depends(require_demo_identity),
):
    response.headers["Cache-Control"] = "no-store"
    return _answer(
        "implementation",
        request,
        identity,
        response,
    )


@router.post("/support")
def support_expert(
    request: ExpertQuestion,
    response: Response,
    identity=Depends(require_demo_identity),
):
    response.headers["Cache-Control"] = "no-store"
    return _answer(
        "support",
        request,
        identity,
        response,
    )