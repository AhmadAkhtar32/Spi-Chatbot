"""Close legacy API bypasses while testing the fictional demo locally."""

import os

from fastapi import Request
from fastapi.responses import JSONResponse

from demo_policy import AccessDenied
from demo_session import verify_demo_session


def install_demo_guard(app) -> None:
    @app.middleware("http")
    async def guard_demo_requests(request: Request, call_next):
        if os.environ.get("ENABLE_DEMO_SESSIONS") != "1":
            return await call_next(request)

        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api/"):
            return await call_next(request)

        if path == "/api/demo/session":
            return await call_next(request)

        if not path.startswith("/api/demo/"):
            return JSONResponse(
                status_code=403,
                content={"detail": "Legacy API is disabled in demo mode"},
            )

        authorization = request.headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator or not token or " " in token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Demo session required"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            request.state.demo_identity = verify_demo_session(token)
        except AccessDenied:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired demo session"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except RuntimeError:
            return JSONResponse(
                status_code=503,
                content={"detail": "Demo session is not configured"},
            )
        return await call_next(request)