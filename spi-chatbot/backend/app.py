"""
FastAPI backend — Step 2 of Atif's plan.

Run: uvicorn app:app --reload

Endpoint:
  POST /api/chat   { "message": "what's the stock of Pepsi?" }
  ->                { "reply": "...", "trace": ["check_stock(item='Pepsi')"] }
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from business_functions import AVAILABLE_FUNCTIONS
from rag import KnowledgeBase, build_answer_prompt
from document_generator import list_templates, generate_document

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.6-flash"
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
# so each one is built once on first use and cached here for reuse across
# requests. Add a new entry here for Support Expert / Project Knowledge
# Expert later — same engine, different folder.
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
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        _knowledge_bases[name] = KnowledgeBase(KNOWLEDGE_DIR / name, client)
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
    interaction_id: str | None = None  # ID of the previous exchange, for follow-ups


class ChatResponse(BaseModel):
    reply: str
    trace: list[str]
    interaction_id: str | None = None  # pass this back in on the next message


def ask_gemini(user_question: str, previous_interaction_id: str | None = None) -> ChatResponse:
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    trace: list[str] = []

    create_kwargs = {"model": GEMINI_MODEL, "input": user_question, "tools": TOOLS}
    if previous_interaction_id:
        # This is what gives the model memory of earlier messages in the
        # same conversation — without it, every message is judged in
        # isolation and "what about its price?" has no idea what "its" means.
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
        return ChatResponse(reply=f"Error calling Gemini: {exc}", trace=[], interaction_id=req.interaction_id)


# --- Implementation Expert (RAG) -------------------------------------------
# Same shared engine (rag.py) will later power Support Expert and Project
# Knowledge Expert too — just pointed at a different "knowledge/<name>" folder.

class ExpertRequest(BaseModel):
    question: str


class ExpertResponse(BaseModel):
    reply: str
    sources: list[str]


@app.post("/api/implementation-expert", response_model=ExpertResponse)
def implementation_expert(req: ExpertRequest):
    if not GEMINI_API_KEY:
        return ExpertResponse(
            reply=(
                "Demo mode: no GEMINI_API_KEY is set yet, so I can't call the real "
                "model. The retrieval pipeline is wired up — add your key to "
                "backend/.env and this will answer for real."
            ),
            sources=[],
        )
    try:
        from google import genai

        kb = get_knowledge_base("implementation")
        relevant_chunks = kb.search(req.question, top_k=5)
        prompt = build_answer_prompt("Implementation Expert", req.question, relevant_chunks)

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)

        sources = sorted({c["source"] for c in relevant_chunks})
        return ExpertResponse(reply=response.text, sources=sources)
    except Exception as exc:
        return ExpertResponse(reply=f"Error calling Gemini: {exc}", sources=[])


@app.post("/api/support-expert", response_model=ExpertResponse)
def support_expert(req: ExpertRequest):
    if not GEMINI_API_KEY:
        return ExpertResponse(
            reply=(
                "Demo mode: no GEMINI_API_KEY is set yet, so I can't call the real "
                "model. The retrieval pipeline is wired up — add your key to "
                "backend/.env and this will answer for real."
            ),
            sources=[],
        )
    try:
        from google import genai

        kb = get_knowledge_base("support")
        relevant_chunks = kb.search(req.question, top_k=5)
        prompt = build_answer_prompt(
            "Support Expert — specializing in incident analysis, troubleshooting, "
            "and root cause suggestions",
            req.question,
            relevant_chunks,
        )

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)

        sources = sorted({c["source"] for c in relevant_chunks})
        return ExpertResponse(reply=response.text, sources=sources)
    except Exception as exc:
        return ExpertResponse(reply=f"Error calling Gemini: {exc}", sources=[])


frontend_dir = Path(__file__).resolve().parent.parent.parent / "spi-chatbot-react" / "dist"
# app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


# --- Project Knowledge Expert (RAG, per-client, upload-based) --------------
# Same rag.py engine as Implementation/Support Expert, but the knowledge
# base folder is chosen per-client at request time (knowledge/project_knowledge/
# <client_id>/), and documents are added via upload rather than pre-loaded —
# this is the one expert scoped to a single customer's own documents.

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

    # The knowledge base for this client is now stale (missing the new
    # document) — drop it from the cache so the next question rebuilds it.
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

    if not GEMINI_API_KEY:
        return ExpertResponse(
            reply=(
                "Demo mode: no GEMINI_API_KEY is set yet, so I can't call the real "
                "model. Upload and retrieval are wired up — add your key to "
                "backend/.env and this will answer for real."
            ),
            sources=[],
        )
    try:
        from google import genai

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

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)

        sources = sorted({c["source"] for c in relevant_chunks})
        return ExpertResponse(reply=response.text, sources=sources)
    except Exception as exc:
        return ExpertResponse(reply=f"Error calling Gemini: {exc}", sources=[])


# --- Document Generator (template filling — deliberately NOT AI-based) ----
# See document_generator.py for why this expert doesn't call Gemini at all.

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


# --- Unified Chat (routes to BI / Implementation / Support internally) ----
# This is what the main chat screen actually calls now. The user never picks
# an expert — a lightweight classification step decides which one handles
# each message, and the licensing check runs before anything answers, so an
# unlicensed category returns a clean "not authorized" message instead of
# revealing which internal expert would have handled it.
#
# Project Knowledge Expert and Document Generator are deliberately NOT part
# of this auto-routing: one needs a specific client/document selected, the
# other needs a structured form. Both stay as their own explicit pages —
# hiding *which conversational expert* answers is a very different thing
# from hiding *tools that need their own UI*.

def classify_intent(message: str, history: list[dict]) -> str:
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])

    prompt = f"""Classify the user's latest message into exactly one category.
Respond with ONLY the category word, nothing else — no punctuation, no explanation.

Categories:
- bi_expert: questions about stock/inventory levels, order status, or finding a screen/menu in the ERP
- implementation_expert: questions about setup, configuration steps, or gap analysis for ERP modules
- support_expert: questions about troubleshooting, incidents, errors, or root causes of problems
- general: greetings, small talk, or anything that doesn't clearly fit the above

Recent conversation:
{history_text}

Latest message: {message}

Category:"""

    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    category = response.text.strip().lower()
    valid = {"bi_expert", "implementation_expert", "support_expert", "general"}
    return category if category in valid else "general"


def _unified_bi_answer(message: str, history: list[dict]) -> tuple[str, list[str]]:
    """Same function-calling logic as /api/chat, but history is folded into
    the prompt text instead of using previous_interaction_id — since a
    unified conversation can jump between expert types turn to turn, a
    single Gemini-side interaction thread isn't a clean fit here."""
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
    from google import genai

    kb = get_knowledge_base(kb_name)
    relevant_chunks = kb.search(message, top_k=5)

    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
    question_with_context = f"Recent conversation:\n{history_text}\n\nCurrent question: {message}" if history else message

    prompt = build_answer_prompt(expert_label, question_with_context, relevant_chunks)
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text


def _unified_general_answer(message: str, history: list[dict]) -> str:
    from google import genai

    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
    prompt = (
        f"You are SPI Assistant, a helpful ERP assistant for D-Biz Solutions. "
        f"Respond naturally and briefly.\n\nRecent conversation:\n{history_text}\n\nMessage: {message}"
        if history
        else f"You are SPI Assistant, a helpful ERP assistant for D-Biz Solutions. "
        f"Respond naturally and briefly.\n\nMessage: {message}"
    )
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text


class UnifiedChatRequest(BaseModel):
    message: str
    history: list[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]


class UnifiedChatResponse(BaseModel):
    reply: str
    trace: list[str] = []


NOT_AUTHORIZED_MESSAGE = (
    "You are not authorized to use this feature. Please contact your administrator "
    "to upgrade your license."
)


@app.post("/api/unified-chat", response_model=UnifiedChatResponse)
def unified_chat(req: UnifiedChatRequest):
    if not GEMINI_API_KEY:
        return UnifiedChatResponse(
            reply=(
                "Demo mode: no GEMINI_API_KEY is set yet, so I can't call the real "
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
        return UnifiedChatResponse(reply=f"Error: {exc}", trace=[])


# --- Voice input (transcription, including Urdu) ---------------------------
# Gemini's audio understanding is multilingual out of the box — a single
# call handles both English and Urdu speech, so no separate Urdu-specific
# pipeline is needed. The transcript is returned in its original language
# and script, then fed into /api/unified-chat exactly like typed text.

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
        response = client.models.generate_content(
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
        raise HTTPException(status_code=500, detail=str(exc))


app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
