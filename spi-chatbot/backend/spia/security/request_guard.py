"""Request gate during the migration to the product access system."""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from spia.api.access import bearer_token, context_for_token


def install_request_guard(app):
    @app.middleware("http")
    async def guard_requests(request: Request, call_next):
        path = request.url.path

        if (
            request.method == "OPTIONS"
            or not path.startswith("/api/")
        ):
            return await call_next(request)

        if path == "/api/v1/session":
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        permitted_path = (
            path.startswith("/api/v1/")
            or path.rstrip("/") == "/api/v1/access"
        )

        if not permitted_path:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "This API has not been migrated "
                        "to the access system"
                    ),
                },
                headers={"Cache-Control": "no-store"},
            )

        try:
            token = bearer_token(
                request.headers.get("authorization")
            )

            context = await run_in_threadpool(
                context_for_token,
                token,
            )

            request.state.access_context = context
            request.state.presenter_identity = (
                context.user,
                context.surface,
            )

        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )

        response = await call_next(request)

        try:
            await run_in_threadpool(
                context_for_token,
                token,
            )

        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )

        response.headers["Cache-Control"] = "no-store"
        return response