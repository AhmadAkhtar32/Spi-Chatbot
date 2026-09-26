"""
FastAPI backend — Step 2 of Atif's plan.

Run: uvicorn app:app --reload

Endpoint:
  POST /api/chat   { "message": "what's the stock of Pepsi?" }
  ->                { "reply": "...", "trace": ["check_stock(item='Pepsi')"] }
"""

import json
import logging
import os
from pathlib import Path

from groq import Groq
from groq_utils import generate_with_retry as groq_generate, friendly_error_message as groq_friendly_error
from gemini_utils import generate_with_retry as gemini_generate, friendly_error_message as gemini_friendly_error

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from business_functions import AVAILABLE_FUNCTIONS
from rag import KnowledgeBase, build_answer_prompt
from document_generator import list_templates, generate_document

logging.basicConfig(level=logging.INFO)
load_dotenv()

# Two providers, two roles:
#   - Groq handles Implementation Expert, Support Expert, and Unified
#     Chat's routing/general-chat text generation.
#   - Embeddings for RAG search run locally (see rag.py) — no external
#     API at all, which removes the embedding-quota bottleneck entirely.
#     (Note: this means sentence-transformers/torch must be deployed
#     wherever this backend runs — see the deployment notes before
#     pushing this to Vercel, since that's a real size constraint there.)
#   - Gemini stays in place for voice transcription (audio understanding)
#     and the BI/function-calling path, since neither has a proven,
#     drop-in Groq equivalent, and BI is unreachable anyway while it's
#     unlicensed in licenses.json.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.5-flash-lite"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = "openai/gpt-oss-120b"

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"

# License config — see licenses.json. There's no login system yet, so this
# is a single fixed "current_user" profile rather than a real per-user
# lookup; that's the one piece a real auth system would replace later.
with open(Path(__file__).resolve().parent / "licenses.json") as f:
    _LICENSES = json.load(f)
CURRENT_USER_LICENSE = _LICENSES.get("current_user", {})

app = FastAPI(title="SPI Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Knowledge bases are expensive to build (they re-embed every document),
# so each one is built once on first use and cached here for reuse
# across requests.
_knowledge_bases: dict[str, KnowledgeBase] = {}


import re

def sanitize_client_id(client_id: str) -> str:
    """Client IDs become folder names on disk, so they're restricted to
    safe characters only — this is the actual access-control boundary
    that keeps one client's documents from ever being reachable via
    another client's ID (e.g. no '..' path traversal)."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", client_id):
        raise ValueError("Invalid client_id: only letters, numbers, - and _ are allowed.")
    return client_id


def invalidate_knowledge_base(name: str):
    """Call this after uploading a new document, so the next search
    re-embeds and includes it instead of serving the stale cached version."""
    _knowledge_bases.pop(name, None)


def get_knowledge_base(name: str) -> KnowledgeBase:
    if name not in _knowledge_bases:
        _knowledge_bases[name] = KnowledgeBase(KNOWLEDGE_DIR / name)
    return _knowledge_bases[name]

TOOLS = [
    {
        "type": "function",
        "name": "check_stock",
        "description": "Get the current stock quantity for a named item.",
        "parameters": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "Name of the item, e.g. 'Pepsi'"}
            },
            "required": ["item"],
        },
    },
    {
        "type": "function",
        "name": "get_order_status",
        "description": "Get the current status of an order given its order ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID, e.g. '1234'"}
            },
            "required": ["order_id"],
        },
    },
    {
        "type": "function",
        "name": "find_menu_location",
        "description": (
            "Business-navigation lookup: given a task the user wants to do in SPI "
            "(e.g. 'add stock', 'create a purchase order'), return which menu/screen handles it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "What the user wants to do, e.g. 'add stock'"}
            },
            "required": ["task"],
        },
    },
]


class ChatRequest(BaseModel):
    message: str
    interaction_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    trace: list[str]
    interaction_id: str | None = None


# --- /api/chat (BI path) stays on Gemini — unreachable while bi_expert is
# unlicensed, and client.interactions.create() has no proven Groq
# equivalent, so it's out of scope for this migration. -------------------

def ask_gemini(user_question: str, previous_interaction_id: str | None = None) -> ChatResponse:
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    trace: list[str] = []

    create_kwargs = {"model": GEMINI_MODEL, "input": user_question, "tools": TOOLS}
    if previous_interaction_id:
        create_kwargs["previous_interaction_id"] = previous_interaction_id

    interaction = client.interactions.create(**create_kwargs)

    while True:
        fc_steps = [s for s in interaction.steps if s.type == "function_call"]
        if not fc_steps:
            break

        function_results = []
        for step in fc_steps:
            func = AVAILABLE_FUNCTIONS[step.name]
            result = func(**step.arguments)
            args_str = ", ".join(f"{k}={v!r}" for k, v in step.arguments.items())
            trace.append(f"{step.name}({args_str})")
            function_results.append(
                {
                    "type": "function_result",
                    "name": step.name,
                    "call_id": step.id,
                    "result": [{"type": "text", "text": result}],
                }
            )

        interaction = client.interactions.create(
            model=GEMINI_MODEL,
            input=function_results,
            tools=TOOLS,
            previous_interaction_id=interaction.id,
        )

    return ChatResponse(reply=interaction.output_text, trace=trace, interaction_id=interaction.id)


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not GEMINI_API_KEY:
        return ChatResponse(
            reply=(
                "Demo mode: no GEMINI_API_KEY is set yet, so I can't call the real "
                "model. The UI, backend, and function-calling pipeline are all wired up — "
                "add your key to backend/.env and this will answer for real."
            ),
            trace=[],
            interaction_id=None,
        )
    try:
        return ask_gemini(req.message, previous_interaction_id=req.interaction_id)
    except Exception as exc:
        return ChatResponse(reply=gemini_friendly_error(exc), trace=[], interaction_id=req.interaction_id)


# --- Implementation Expert (RAG) — generation on Groq, embeddings local -

class ExpertRequest(BaseModel):
    question: str


class ExpertResponse(BaseModel):
    reply: str
    sources: list[str]


@app.post("/api/implementation-expert", response_model=ExpertResponse)
def implementation_expert(req: ExpertRequest):
    if not GROQ_API_KEY:
        return ExpertResponse(
            reply=(
                "Demo mode: no GROQ_API_KEY is set yet, so I can't call the real "
                "model. The retrieval pipeline is wired up — add your key to "
                "backend/.env and this will answer for real."
            ),
            sources=[],
        )
    try:
        kb = get_knowledge_base("implementation")
        relevant_chunks = kb.search(req.question, top_k=5)
        prompt = build_answer_prompt("Implementation Expert", req.question, relevant_chunks)

        client = Groq(api_key=GROQ_API_KEY)
        response = groq_generate(client, model=GROQ_MODEL, messages=[{"role": "user", "content": prompt}])

        sources = sorted({c["source"] for c in relevant_chunks})
        return ExpertResponse(reply=response.choices[0].message.content, sources=sources)
    except Exception as exc:
        return ExpertResponse(reply=groq_friendly_error(exc), sources=[])


@app.post("/api/support-expert", response_model=ExpertResponse)
def support_expert(req: ExpertRequest):
    if not GROQ_API_KEY:
        return ExpertResponse(
            reply=(
                "Demo mode: no GROQ_API_KEY is set yet, so I can't call the real "
                "model. The retrieval pipeline is wired up — add your key to "
                "backend/.env and this will answer for real."
            ),
            sources=[],
        )
    try:
        kb = get_knowledge_base("support")
        relevant_chunks = kb.search(req.question, top_k=5)
        prompt = build_answer_prompt(
            "Support Expert — specializing in incident analysis, troubleshooting, "
            "and root cause suggestions",
            req.question,
            relevant_chunks,
        )

        client = Groq(api_key=GROQ_API_KEY)
        response = groq_generate(client, model=GROQ_MODEL, messages=[{"role": "user", "content": prompt}])

        sources = sorted({c["source"] for c in relevant_chunks})
        return ExpertResponse(reply=response.choices[0].message.content, sources=sources)
    except Exception as exc:
        return ExpertResponse(reply=groq_friendly_error(exc), sources=[])


frontend_dir = Path(__file__).resolve().parent.parent.parent / "spi-chatbot-react" / "dist"


# --- Project Knowledge Expert (RAG, per-client, upload-based) — Groq ----

PROJECT_KNOWLEDGE_ROOT = "project_knowledge"


@app.post("/api/project-knowledge/upload")
async def upload_project_document(client_id: str = Form(...), file: UploadFile = File(...)):
    try:
        safe_client_id = sanitize_client_id(client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=400,
            detail="Only .txt files are supported right now. PDF/DOCX extraction can be added later.",
        )

    client_folder = KNOWLEDGE_DIR / PROJECT_KNOWLEDGE_ROOT / safe_client_id
    client_folder.mkdir(parents=True, exist_ok=True)

    contents = await file.read()
    (client_folder / file.filename).write_bytes(contents)

    invalidate_knowledge_base(f"{PROJECT_KNOWLEDGE_ROOT}/{safe_client_id}")

    return {"status": "uploaded", "filename": file.filename, "client_id": safe_client_id}


@app.get("/api/project-knowledge/documents")
def list_project_documents(client_id: str):
    try:
        safe_client_id = sanitize_client_id(client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    client_folder = KNOWLEDGE_DIR / PROJECT_KNOWLEDGE_ROOT / safe_client_id
    if not client_folder.exists():
        return {"documents": []}
    return {"documents": sorted(p.name for p in client_folder.glob("*.txt"))}


class ProjectKnowledgeRequest(BaseModel):
    client_id: str
    question: str


@app.post("/api/project-knowledge/chat", response_model=ExpertResponse)
def project_knowledge_expert(req: ProjectKnowledgeRequest):
    try:
        safe_client_id = sanitize_client_id(req.client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not GROQ_API_KEY:
        return ExpertResponse(
            reply=(
                "Demo mode: no GROQ_API_KEY is set yet, so I can't call the real "
                "model. Upload and retrieval are wired up — add your key to "
                "backend/.env and this will answer for real."
            ),
            sources=[],
        )
    try:
        kb = get_knowledge_base(f"{PROJECT_KNOWLEDGE_ROOT}/{safe_client_id}")
        relevant_chunks = kb.search(req.question, top_k=5)

        if not relevant_chunks:
            return ExpertResponse(
                reply=(
                    f"No documents have been uploaded yet for client '{safe_client_id}'. "
                    "Upload a document first, then ask again."
                ),
                sources=[],
            )

        prompt = build_answer_prompt(
            f"Project Knowledge Expert for client '{safe_client_id}'",
            req.question,
            relevant_chunks,
        )

        client = Groq(api_key=GROQ_API_KEY)
        response = groq_generate(client, model=GROQ_MODEL, messages=[{"role": "user", "content": prompt}])

        sources = sorted({c["source"] for c in relevant_chunks})
        return ExpertResponse(reply=response.choices[0].message.content, sources=sources)
    except Exception as exc:
        return ExpertResponse(reply=groq_friendly_error(exc), sources=[])


# --- Document Generator (template filling — NOT AI-based, unaffected) ---

@app.get("/api/document-generator/templates")
def get_document_templates():
    return {"templates": list_templates()}


class DocumentGenerateRequest(BaseModel):
    template_id: str
    fields: dict[str, str]


@app.post("/api/document-generator/generate")
def generate_document_endpoint(req: DocumentGenerateRequest):
    try:
        return generate_document(req.template_id, req.fields)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# --- Unified Chat (routes to BI / Implementation / Support internally) ---
# Routing/classification, Implementation, Support, and general chat all
# run on Groq now, with local embeddings for search. Only bi_expert
# (unreachable, unlicensed) still touches Gemini, via _unified_bi_answer.

def classify_intent(message: str, history: list[dict]) -> str:
    client = Groq(api_key=GROQ_API_KEY)
    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])

    prompt = f"""Classify the user's latest message into exactly one category.
Respond with ONLY the category word, nothing else — no punctuation, no explanation.

Categories:
- bi_expert: asking for a CURRENT live value — e.g. "what's the stock of X", "what's the status of order #123", or asking which menu/screen to use for a task
- implementation_expert: questions about setup, configuration steps, or gap analysis for ERP modules
- support_expert: questions about WHY something went wrong, an error, an incident, or a root cause — even if the question also mentions stock, inventory, or orders. If the question describes a problem or asks "why would X happen", it is support_expert, not bi_expert, regardless of which words appear in it.
- general: greetings, small talk, or anything that doesn't clearly fit the above

Recent conversation:
{history_text}

Latest message: {message}

Category:"""

    response = groq_generate(client, model=GROQ_MODEL, messages=[{"role": "user", "content": prompt}])
    category = response.choices[0].message.content.strip().lower()
    valid = {"bi_expert", "implementation_expert", "support_expert", "general"}
    return category if category in valid else "general"


def _unified_bi_answer(message: str, history: list[dict]) -> tuple[str, list[str]]:
    """Unreachable while bi_expert is unlicensed — stays on Gemini."""
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    trace: list[str] = []

    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
    input_text = f"Recent conversation:\n{history_text}\n\nCurrent question: {message}" if history else message

    interaction = client.interactions.create(model=GEMINI_MODEL, input=input_text, tools=TOOLS)

    while True:
        fc_steps = [s for s in interaction.steps if s.type == "function_call"]
        if not fc_steps:
            break
        function_results = []
        for step in fc_steps:
            func = AVAILABLE_FUNCTIONS[step.name]
            result = func(**step.arguments)
            args_str = ", ".join(f"{k}={v!r}" for k, v in step.arguments.items())
            trace.append(f"{step.name}({args_str})")
            function_results.append(
                {"type": "function_result", "name": step.name, "call_id": step.id, "result": [{"type": "text", "text": result}]}
            )
        interaction = client.interactions.create(
            model=GEMINI_MODEL, input=function_results, tools=TOOLS, previous_interaction_id=interaction.id
        )

    return interaction.output_text, trace


def _unified_rag_answer(kb_name: str, expert_label: str, message: str, history: list[dict]) -> str:
    kb = get_knowledge_base(kb_name)
    relevant_chunks = kb.search(message, top_k=5)

    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
    question_with_context = f"Recent conversation:\n{history_text}\n\nCurrent question: {message}" if history else message

    prompt = build_answer_prompt(expert_label, question_with_context, relevant_chunks)
    client = Groq(api_key=GROQ_API_KEY)
    response = groq_generate(client, model=GROQ_MODEL, messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content


def _unified_general_answer(message: str, history: list[dict]) -> str:
    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
    prompt = (
        f"You are SPI Assistant, a helpful ERP assistant for D-Biz Solutions. "
        f"Respond naturally and briefly.\n\nRecent conversation:\n{history_text}\n\nMessage: {message}"
        if history
        else f"You are SPI Assistant, a helpful ERP assistant for D-Biz Solutions. "
        f"Respond naturally and briefly.\n\nMessage: {message}"
    )
    client = Groq(api_key=GROQ_API_KEY)
    response = groq_generate(client, model=GROQ_MODEL, messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content


class UnifiedChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class UnifiedChatResponse(BaseModel):
    reply: str
    trace: list[str] = []


NOT_AUTHORIZED_MESSAGE = (
    "You are not authorized to use this feature. Please contact your administrator "
    "to upgrade your license."
)


@app.post("/api/unified-chat", response_model=UnifiedChatResponse)
def unified_chat(req: UnifiedChatRequest):
    if not GROQ_API_KEY:
        return UnifiedChatResponse(
            reply=(
                "Demo mode: no GROQ_API_KEY is set yet, so I can't call the real "
                "model. The routing and licensing pipeline are wired up — add your "
                "key to backend/.env and this will answer for real."
            ),
            trace=[],
        )
    try:
        expert_id = classify_intent(req.message, req.history)

        if expert_id != "general" and not CURRENT_USER_LICENSE.get(expert_id, False):
            return UnifiedChatResponse(reply=NOT_AUTHORIZED_MESSAGE, trace=[])

        if expert_id == "bi_expert":
            reply, trace = _unified_bi_answer(req.message, req.history)
            return UnifiedChatResponse(reply=reply, trace=trace)
        elif expert_id == "implementation_expert":
            reply = _unified_rag_answer("implementation", "Implementation Expert", req.message, req.history)
            return UnifiedChatResponse(reply=reply, trace=[])
        elif expert_id == "support_expert":
            reply = _unified_rag_answer("support", "Support Expert", req.message, req.history)
            return UnifiedChatResponse(reply=reply, trace=[])
        else:
            reply = _unified_general_answer(req.message, req.history)
            return UnifiedChatResponse(reply=reply, trace=[])
    except Exception as exc:
        return UnifiedChatResponse(reply=groq_friendly_error(exc), trace=[])


# --- Voice input (transcription, including Urdu) — stays on Gemini -------

@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=400, detail="No GEMINI_API_KEY set yet — add it to backend/.env.")
    try:
        from google import genai
        from google.genai import types

        audio_bytes = await file.read()
        mime_type = file.content_type or "audio/webm"

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = gemini_generate(
            client,
            model=GEMINI_MODEL,
            contents=[
                "Transcribe this audio clip exactly as spoken. It may be in English or Urdu. "
                "Preserve the original language and script (write Urdu in Urdu script, not "
                "transliterated). Output ONLY the transcription text — no labels, no explanation.",
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ],
        )
        return {"transcript": response.text.strip()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=gemini_friendly_error(exc))


if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")