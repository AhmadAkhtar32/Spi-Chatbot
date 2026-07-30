"""
FastAPI backend — Step 2 of Atif's plan.

Run: uvicorn app:app --reload

Endpoint:
  POST /api/chat   { "message": "what's the stock of Pepsi?" }
  ->                { "reply": "...", "trace": ["check_stock(item='Pepsi')"] }
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from business_functions import AVAILABLE_FUNCTIONS
from rag import KnowledgeBase, build_answer_prompt

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.6-flash"
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"

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


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
