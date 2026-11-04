"""Authenticated history APIs and capture of existing server answers."""
import base64
import hashlib
import json
import logging
import threading
import warnings
from io import BytesIO
from typing import Literal
from urllib.parse import parse_qs
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from spia.api.access import require_access_context
from spia.security.access_control import AccessDenied
from spia.security.store import SecurityConfigurationError
from spia.services import chat_history as history
from spia.services.knowledge import KnowledgeUnavailable

router = APIRouter(prefix="/api/v1/conversations", tags=["Personal history"])
_image_slots = threading.BoundedSemaphore(2)
BUSINESS_NOTICES = frozenset({
    "Choose one area: stock, sales orders, purchase orders, payroll, tickets or credit returns.",
    "Employee filtering is available for payroll.",
    "Enter a question of up to 2,000 characters.",
    "For payroll, use a month such as September 2026. Stock search has no date filter.",
    "Include the year with the month, for example September 2026.",
    "Party filtering is available for sales, purchases and credit returns.",
    "Request between 1 and 100 records per page.",
    "Run a search first, then ask for the next or previous page.",
    "Run the search again before changing pages.",
    "Search one record, item, warehouse, party or employee at a time.",
    "Shorten the record search phrase to 100 characters.",
    "There are no more matching records.",
    "This request needs BI access. A licensed user can open the BI expert tab for supported summaries. Revenue, profit and forecasts need additional data and are not available in this sample.",
    "To generate a document, open the Document generator tab if it is available for your account. Business records searches existing data.",
    "Use a direct record search with explicit dates or a payroll month. Comparisons, exclusions and relative dates are not supported in this step.",
    "Use a warehouse code, for example WH-LHR, when specifying a location. Item-name searches can also run across your permitted warehouses.",
    "Use an item, party or employee search phrase of up to 100 characters.",
    "Use full YYYY-MM-DD dates for this area.",
    "Use one date or one date range.",
    "Use one payroll month per question.",
    "Use one status per question.",
    "Use one ticket module per question.",
    "Use the stock area for item and warehouse searches.",
    "You are already on the first page.",
    "Zero-stock filtering is not available in this screen yet. Ask for an item or for available stock.",
    "This suggested record link is invalid. Refresh the questions.",
})


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scope(Strict):
    view: Literal["knowledge", "company", "business"]
    expert: Literal["support", "implementation"] | None = None
    module: Literal["financial", "inventory", "payroll"] | None = None

    @model_validator(mode="after")
    def complete(self):
        if self.view == "knowledge" and (not self.expert or not self.module):
            raise ValueError("Choose an expert and module")
        if self.view != "knowledge" and (self.expert or self.module):
            raise ValueError("Expert/module only apply to document conversations")
        return self


class Create(Strict):
    id: str
    scope: Scope


class Rename(Strict):
    title: str = Field(min_length=1, max_length=120)
    revision: int = Field(strict=True, ge=1)


class Fork(Strict):
    message_id: str
    title: str = Field(default="Edited question", min_length=1, max_length=120)


class Notice(Strict):
    question: str = Field(min_length=1, max_length=2000)
    notice: str = Field(min_length=1, max_length=1000)
    request_id: str


def run(operation):
    try:
        return operation()
    except AccessDenied as exc:
        history.fail(403, exc.code)
    except HTTPException:
        raise
    except (SecurityConfigurationError, KnowledgeUnavailable):
        history.fail(503, "Current access or approved knowledge is unavailable")
    except Exception as exc:
        logging.getLogger(__name__).error("History operation failed: %s", type(exc).__name__)
        history.fail(503, "Personal history storage is unavailable")


@router.get("/status")
def status(context=Depends(require_access_context)):
    if not history.enabled():
        return {"enabled": False, "notice": "Persistent history needs the local/company-hosted app. This deployment keeps session-only chats."}
    def check():
        with history.connection() as db:
            db.execute("SELECT 1")
        return {"enabled": True, "max_conversations": history.limit("SPIA_MAX_CHATS_PER_USER", 100),
                "max_messages": history.limit("SPIA_MAX_MESSAGES_PER_CHAT", 500)}
    return run(check)


@router.post("")
def create(body: Create, context=Depends(require_access_context)):
    return run(lambda: history.create(context, body.id, body.scope.model_dump(exclude_none=True)))


@router.get("")
def listing(q: str = "", before_time: int | None = None, before_id: str | None = None,
            limit: int = 20, context=Depends(require_access_context)):
    if len(q) > 120 or not 1 <= limit <= 50 or (before_time is None) != (before_id is None):
        history.fail(422, "Invalid history search or page")
    cursor = (before_time, history.identifier(before_id)) if before_id else None
    return run(lambda: history.listing(context, q.strip(), cursor, limit))


@router.get("/{conversation_id}/messages")
def messages(conversation_id: str, after: int = -1, before: int | None = None,
             limit: int = 50, context=Depends(require_access_context)):
    return run(lambda: history.messages(context, conversation_id, after, limit, before=before))


@router.post("/{conversation_id}/rename")
def rename(conversation_id: str, body: Rename, context=Depends(require_access_context)):
    return run(lambda: history.rename(context, conversation_id, body.title, body.revision))


@router.post("/{conversation_id}/delete")
def delete(conversation_id: str, context=Depends(require_access_context)):
    run(lambda: history.delete(context, conversation_id))
    return {"deleted": True}


@router.post("/{conversation_id}/fork")
def fork(conversation_id: str, body: Fork, context=Depends(require_access_context)):
    return run(lambda: history.fork(context, conversation_id, body.message_id, body.title))


@router.post("/{conversation_id}/notice")
def notice(conversation_id: str, body: Notice, context=Depends(require_access_context)):
    if body.notice not in BUSINESS_NOTICES or not body.question.strip():
        history.fail(422, "Use an approved business-query notice")
    def save():
        with history.connection() as db:
            row = history.row_for(db, context, conversation_id)
            if json.loads(row["scope"]) != {"view": "business"}:
                history.fail(409, "Business notices need a business conversation")
        fingerprint = hashlib.sha256(history.encode([body.question, body.notice]).encode()).hexdigest()
        _, previous = history.claim(context, conversation_id, body.request_id, fingerprint)
        if previous is not None:
            return previous["body"]
        try:
            return history.finish(context, conversation_id, body.request_id, body.question.strip(),
                {"reply": body.notice, "sources": [], "language": "en", "clarification": True})
        except BaseException:
            history.abandon(body.request_id)
            raise
    return run(save)


@router.get("/{conversation_id}/export")
def export(conversation_id: str, context=Depends(require_access_context)):
    def transcript():
        rows, after = [], -1
        while True:
            page = history.messages(context, conversation_id, after, 100)
            for item in page["messages"]:
                if item.pop("image_base64", None):
                    item["attachment"] = "Screenshot attached"
                rows.append(item)
            if page["next_after"] is None:
                break
            after = page["next_after"]
        return {"schema": "spia-transcript-v1", "conversation": page["conversation"], "messages": rows}
    result = run(transcript)
    return Response(history.encode(result), media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="conversation-{conversation_id}.json"', "Cache-Control": "no-store"})


def route_kind(path, method):
    if method == "POST" and path == "/api/v1/experts/document-question":
        return "file"
    if method == "POST" and path in {"/api/v1/experts/support", "/api/v1/experts/implementation",
                                    "/api/v1/experts/project-knowledge", "/api/v1/experts/image-question"}:
        return "image" if path.endswith("/image-question") else "document"
    if method == "GET" and path.startswith("/api/v1/business/"):
        if path.removeprefix("/api/v1/business/").split("/")[0] in {
            "stock", "sales-orders", "purchase-orders", "credit-return-notes", "payroll", "tickets"}:
            return "business"
    return None


def check_scope(context, cid, path, query, body, kind):
    with history.connection() as db:
        row = history.row_for(db, context, cid)
        view = history.authorize(context, row)
    scope = json.loads(row["scope"])
    if kind == "business":
        matches = scope == {"view": "business"}
    elif path.endswith("/project-knowledge"):
        matches = scope == {"view": "company"}
    elif scope.get("view") != "knowledge":
        matches = False
    elif kind in {"image", "file"}:
        params = parse_qs(query.decode("ascii"))
        matches = params.get("expert") == [scope["expert"]+"_expert"] and params.get("module") == [scope["module"]]
    else:
        matches = path.rsplit("/", 1)[-1] == scope["expert"] and body.get("module") == scope["module"]
    if not matches:
        history.fail(409, "Request does not match the conversation context")
    return row, view


def clean_image(raw, media_type):
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not _image_slots.acquire(blocking=False):
        history.fail(429, "Image service is busy; try again shortly")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                if image.format != {"image/png": "PNG", "image/jpeg": "JPEG"}[media_type] or getattr(image, "n_frames", 1) != 1:
                    raise ValueError()
                width, height = image.size
                if min(width, height) < 16 or max(width, height) > 4096 or width*height > 8000000:
                    raise ValueError()
                image.verify()
            with Image.open(BytesIO(raw)) as image, BytesIO() as output:
                clean = ImageOps.exif_transpose(image).convert("RGB")
                try:
                    clean.thumbnail((1600, 1600))
                    clean.save(output, format="JPEG", quality=90)
                    return output.getvalue()
                finally:
                    clean.close()
    except (KeyError, ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        history.fail(422, "Use a valid PNG or JPEG, 16-4096 pixels per side and at most 8 megapixels")
    finally:
        _image_slots.release()


async def read_limited(receive, maximum):
    raw = bytearray()
    while True:
        event = await receive()
        if event["type"] == "http.disconnect":
            return None
        raw.extend(event.get("body", b""))
        if len(raw) > maximum:
            history.fail(413, "Conversation input exceeds limits")
        if not event.get("more_body", False):
            return bytes(raw)


class HistoryCapture:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["method"] == "POST" and scope["path"].startswith("/api/v1/conversations"):
            original_receive = receive
            try:
                raw_body = await read_limited(receive, 16384)
            except HTTPException as exc:
                return await JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                    headers={"Cache-Control": "no-store"})(scope, receive, send)
            if raw_body is None:
                return
            first = True
            async def history_body():
                nonlocal first
                if first:
                    first = False
                    return {"type": "http.request", "body": raw_body, "more_body": False}
                return await original_receive()
            return await self.app(scope, history_body, send)
        pairs = scope.get("headers", [])
        headers = {k.lower(): v for k, v in pairs}
        kind = route_kind(scope["path"], scope["method"])
        if not kind or not ({b"x-spia-conversation", b"x-spia-request-id"} & headers.keys()):
            return await self.app(scope, receive, send)
        claimed = None
        try:
            context = scope.get("state", {}).get("access_context")
            if context is None:
                history.fail(401, "A valid session is required")
            for name in (b"x-spia-conversation", b"x-spia-request-id", b"x-spia-question", b"content-type"):
                if sum(k.lower() == name for k, _ in pairs) > 1:
                    history.fail(422, "Duplicate conversation request headers")
            cid = history.identifier(headers.get(b"x-spia-conversation", b"").decode("ascii"))
            rid = history.identifier(headers.get(b"x-spia-request-id", b"").decode("ascii"))
            query = scope.get("query_string", b"")
            if len(query) > 8192:
                history.fail(422, "Request query exceeds limits")
            raw, body, image, attachment = bytearray(), {}, None, None
            original_receive = receive
            if scope["method"] == "POST":
                raw = await read_limited(original_receive, 2*1024*1024 if kind in {"image", "file"} else 8192)
                if raw is None:
                    return
                if kind == "document":
                    body = json.loads(raw)
                    if not isinstance(body, dict):
                        history.fail(422, "Use a question object")
                    question = body.get("question", "")
                else:
                    encoded = headers.get(b"x-spia-question")
                    if encoded is not None and len(encoded) > 6000:
                        history.fail(422, "Question header exceeds limits")
                    question = base64.b64decode(encoded, validate=True).decode("utf-8") if encoded is not None else ("Summarize this document in English." if kind == "file" else "Explain this ERP screen or error in English.")
                first = True
                async def replay():
                    nonlocal first
                    if first:
                        first = False
                        return {"type": "http.request", "body": bytes(raw), "more_body": False}
                    return await original_receive()
                receive = replay
            else:
                encoded = headers.get(b"x-spia-question", b"")
                if len(encoded) > 12000:
                    history.fail(422, "Question header exceeds limits")
                question = base64.b64decode(encoded, validate=True).decode("utf-8")
            if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
                history.fail(422, "A question is required for history")
            row, view = await run_in_threadpool(check_scope, context, cid, scope["path"], query, body, kind)
            media_type = headers.get(b"content-type", b"").decode("ascii").split(";")[0].strip().lower()
            if kind == "image":
                if media_type not in {"image/png", "image/jpeg"}:
                    history.fail(415, "Upload one PNG or JPEG screenshot")
                image = await run_in_threadpool(clean_image, bytes(raw), media_type)
            if kind == "file":
                from spia.services.chat_files import upload
                params = parse_qs(query.decode("ascii"))
                if set(params) != {"expert", "module", "filename"} or any(len(v) != 1 for v in params.values()):
                    history.fail(422, "Supply expert, module and filename once each")
                attachment = upload(bytes(raw), media_type, params["filename"][0])
            fingerprint = hashlib.sha256(history.encode({"method": scope["method"], "path": scope["path"],
                "query": base64.b64encode(query).decode(), "body": hashlib.sha256(raw).hexdigest(),
                "question": question, "media_type": media_type}).encode()).hexdigest()
            _, previous = await run_in_threadpool(history.claim, context, cid, rid, fingerprint)
            if previous is not None:
                saved = previous["body"]
                if view is not None and "reply" in saved:
                    from spia.api.experts import document_reply
                    chat_scope = json.loads(row["scope"])
                    saved.update(await run_in_threadpool(document_reply, context, view,
                        chat_scope.get("expert", "project_knowledge"), chat_scope.get("module", "project"),
                        saved["reply"], saved.get("sources", []), saved.get("language", "en")))
                await run_in_threadpool(history.authorize, context, row)
                return await JSONResponse(saved, status_code=previous["status"], headers={"Cache-Control": "no-store"})(scope, receive, send)
            claimed = rid
            start, chunks, size = None, [], 0
            async def capture(event):
                nonlocal start, size
                if event["type"] == "http.response.start":
                    start = event
                elif event["type"] == "http.response.body":
                    size += len(event.get("body", b""))
                    if size > 2*1024*1024:
                        history.fail(503, "Response exceeds history limits")
                    chunks.append(event.get("body", b""))
            await self.app(scope, receive, capture)
            if start is None:
                history.fail(503, "The assistant response was interrupted")
            original = json.loads(b"".join(chunks))
            if not isinstance(original, dict):
                history.fail(503, "Unexpected conversation response")
            status_code = start["status"]
            if 200 <= status_code < 300:
                if not ("reply" in original or "kind" in original):
                    history.fail(503, "Unexpected conversation response")
                if body.get("source"):
                    original["history_source"] = body["source"]
                result = await run_in_threadpool(history.finish, context, cid, rid, question.strip(), original, image, attachment=attachment)
            elif 400 <= status_code < 600:
                from spia.integrations.groq import question_language
                notice = {"reply": f"The request could not be completed (HTTP {status_code}). Please check the request or try again.",
                          "language": question_language(question), "sources": [], "history_error": status_code}
                if notice["language"] == "ur":
                    notice["reply"] = "\u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0645\u06a9\u0645\u0644 \u0646\u06c1\u06cc\u06ba \u06c1\u0648 \u0633\u06a9\u06cc\u06d4 \u0628\u0631\u0627\u06c1 \u06a9\u0631\u0645 \u0633\u0648\u0627\u0644 \u0686\u06cc\u06a9 \u06a9\u0631\u06cc\u06ba \u06cc\u0627 \u062f\u0648\u0628\u0627\u0631\u06c1 \u06a9\u0648\u0634\u0634 \u06a9\u0631\u06cc\u06ba\u06d4" + f" (HTTP {status_code})"
                if view is not None and body.get("source") in view.sources:
                    notice["history_source"] = body["source"]
                saved = await run_in_threadpool(history.finish, context, cid, rid, question.strip(), notice, image, status_code)
                result = original | {"history": saved["history"]}
            else:
                history.fail(503, "Unexpected conversation response")
            claimed = None
            raw_response = history.encode(result).encode("utf-8")
            start["headers"] = [(k, v) for k, v in start["headers"] if k.lower() not in {b"content-length", b"etag"}]
            start["headers"].append((b"content-length", str(len(raw_response)).encode("ascii")))
            await send(start)
            await send({"type": "http.response.body", "body": raw_response})
        except HTTPException as exc:
            await JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers={"Cache-Control": "no-store"})(scope, receive, send)
        except AccessDenied as exc:
            await JSONResponse({"detail": exc.code}, status_code=403, headers={"Cache-Control": "no-store"})(scope, receive, send)
        except (ValueError, UnicodeError, TypeError):
            await JSONResponse({"detail": "Invalid conversation request"}, status_code=422, headers={"Cache-Control": "no-store"})(scope, receive, send)
        except Exception as exc:
            logging.getLogger(__name__).error("History capture failed: %s", type(exc).__name__)
            await JSONResponse({"detail": "Personal history could not be saved. Refresh before retrying."}, status_code=503, headers={"Cache-Control": "no-store"})(scope, receive, send)
        finally:
            if claimed:
                try:
                    await run_in_threadpool(history.abandon, claimed)
                except Exception as exc:
                    logging.getLogger(__name__).error("History cleanup failed: %s", type(exc).__name__)


def install_history(app):
    if getattr(app.state, "spia_history_installed", False):
        return
    app.include_router(router)
    app.add_middleware(HistoryCapture)
    from fastapi.middleware.cors import CORSMiddleware
    for entry in app.user_middleware:
        if entry.cls is CORSMiddleware:
            headers = list(entry.kwargs.get("allow_headers", []))
            for name in ("X-SPIA-Conversation", "X-SPIA-Request-ID", "X-SPIA-Question"):
                if name.lower() not in {h.lower() for h in headers}:
                    headers.append(name)
            entry.kwargs["allow_headers"] = headers
    app.state.spia_history_installed = True

# SPIA_PRIVATE_DOCUMENT_DOWNLOAD_V1
@router.get("/{conversation_id}/attachments/{message_id}")
def attachment_download(conversation_id: str, message_id: str, context=Depends(require_access_context)):
    from urllib.parse import quote
    from spia.services.chat_files import download
    item = run(lambda: download(context, conversation_id, message_id))
    return Response(item["content"], media_type=item["media_type"], headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(item["filename"], safe=""),
    })
