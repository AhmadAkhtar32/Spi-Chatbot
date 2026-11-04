
"""Attach a document to one permitted expert conversation."""
import base64
import binascii
import os
from typing import Literal
from fastapi import Depends, Request, Response
from starlette.concurrency import run_in_threadpool
from spia.api.access import require_access_context
from spia.services import chat_files

def install(router):
    @router.post("/document-question")
    async def document_question(request: Request, response: Response, filename: str,
        expert: Literal["support_expert", "implementation_expert"],
        module: Literal["financial", "inventory", "payroll"],
        context=Depends(require_access_context)):
        from spia.api import experts
        view = await run_in_threadpool(experts.access, context, expert.removesuffix("_expert"), module)
        if os.environ.get("SPIA_ENABLE_DOCUMENT_INPUT", "1") != "1":
            experts.fail(404, "Document input is disabled")
        if set(request.query_params) != {"expert", "module", "filename"} or any(len(request.query_params.getlist(k)) != 1 for k in request.query_params):
            experts.fail(422, "Supply expert, module and filename once each")
        for name in ("content-type", "x-spia-question"):
            if len(request.headers.getlist(name)) > 1:
                experts.fail(422, "Duplicate document request headers")
        try:
            encoded = request.headers.get("X-SPIA-Question", "")
            if len(encoded) > 6000:
                raise ValueError()
            question = base64.b64decode(encoded, validate=True).decode("utf-8").strip() if encoded else "Summarize this document in English."
            if not 3 <= len(question) <= 1000:
                raise ValueError()
        except (ValueError, binascii.Error, UnicodeError):
            experts.fail(422, "Enter a question between 3 and 1000 characters")
        raw = bytearray()
        async for part in request.stream():
            raw.extend(part)
            if len(raw) > chat_files.MAX_BYTES:
                experts.fail(413, "Document exceeds 2 MiB")
        document = chat_files.upload(bytes(raw), request.headers.get("content-type", "").split(";")[0].strip().lower(), filename)
        await run_in_threadpool(experts.confirm, view)
        content = await run_in_threadpool(chat_files.text, document)
        await run_in_threadpool(experts.confirm, view)
        body = experts.ExpertQuestion(module=module, question=question, source=None)
        return await run_in_threadpool(lambda: experts.answer(expert.removesuffix("_expert"), body, context, response, use_cache=False, attachment_text=content))
