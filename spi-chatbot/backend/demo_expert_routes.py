"""Role- and module-checked document experts for fictional demo users."""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from demo_policy import AccessDenied, authorize_expert
from demo_routes import require_demo_identity
from groq_utils import generate_with_retry
from rag import KnowledgeBase, build_answer_prompt, cosine_similarity, embed_texts


router = APIRouter(prefix="/api/demo/experts", tags=["Demo experts"])
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
MIN_SCORE = 0.35  # Demo tuning value, not a guarantee of answer accuracy.


class ExpertQuestion(BaseModel):
    module: Literal["financial", "inventory", "payroll"]
    question: str = Field(min_length=3, max_length=1000)


@lru_cache(maxsize=2)
def _knowledge_base(name: str) -> KnowledgeBase:
    return KnowledgeBase(KNOWLEDGE_DIR / name)


def _answer(name: str, request: ExpertQuestion, identity: tuple[dict, str]) -> dict:
    user, surface = identity
    expert_id = f"{name}_expert"
    try:
        authorize_expert(user, surface, expert_id, request.module)
    except AccessDenied:
        raise HTTPException(status_code=403, detail="Expert or module is not licensed") from None

    question = request.question.strip()
    if len(question) < 3:
        raise HTTPException(status_code=400, detail="Enter a longer question")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI service is not configured")

    try:
        kb = _knowledge_base(name)
        # Filter BEFORE ranking and before sending context to Groq. Generic
        # or ambiguously tagged documents are excluded until reviewed.
        allowed = [c for c in kb.chunks if c.get("module") == request.module]
        if not allowed:
            return {"reply": "No approved reference material for this module.", "sources": []}

        vector = embed_texts([question])[0]
        ranked = sorted(
            allowed,
            key=lambda chunk: cosine_similarity(vector, chunk["embedding"]),
            reverse=True,
        )[:5]
        if cosine_similarity(vector, ranked[0]["embedding"]) < MIN_SCORE:
            return {"reply": "I could not find this in the approved reference material.", "sources": []}

        prompt = build_answer_prompt(
            "SPI " + name.capitalize() + " Expert", question, ranked
        )
        from groq import Groq

        response = generate_with_retry(
            Groq(api_key=api_key),
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
        )
        return {
            "reply": response.choices[0].message.content or "",
            "sources": sorted({c["source"] for c in ranked}),
        }
    except Exception:
        logging.exception("Demo %s expert failed", name)
        raise HTTPException(status_code=502, detail="Expert service is unavailable") from None


@router.post("/implementation")
def implementation_expert(
    request: ExpertQuestion, identity: tuple[dict, str] = Depends(require_demo_identity)
):
    return _answer("implementation", request, identity)


@router.post("/support")
def support_expert(
    request: ExpertQuestion, identity: tuple[dict, str] = Depends(require_demo_identity)
):
    return _answer("support", request, identity)