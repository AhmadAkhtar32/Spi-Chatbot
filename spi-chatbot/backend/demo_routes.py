"""Presenter-only demo session endpoints; never use as SPIA authentication."""

import os

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel

from demo_policy import AccessDenied
from demo_session import SESSION_SECONDS, issue_demo_session, verify_demo_session


router = APIRouter(prefix="/api/demo", tags=["Demo access"])


class DemoLoginRequest(BaseModel):
    user_id: str
    surface: str
    pin: str


def _require_demo_enabled() -> None:
    if os.environ.get("ENABLE_DEMO_SESSIONS") != "1":
        raise HTTPException(status_code=404, detail="Demo sessions are disabled")


def require_demo_identity(authorization: str | None = Header(default=None)) -> tuple[dict, str]:
    """For future demo APIs: derive identity and surface from a signed token."""
    _require_demo_enabled()
    scheme, separator, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not token or " " in token:
        raise HTTPException(
            status_code=401,
            detail="Demo session required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return verify_demo_session(token)
    except AccessDenied:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired demo session",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Demo session is not configured") from None


@router.post("/session")
def create_demo_session(body: DemoLoginRequest, response: Response):
    """A presenter chooses a fictional user; this is disabled by default."""
    _require_demo_enabled()
    response.headers["Cache-Control"] = "no-store"
    try:
        token = issue_demo_session(body.user_id, body.surface, body.pin)
    except AccessDenied:
        raise HTTPException(status_code=401, detail="Invalid demo credentials") from None
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Demo session is not configured") from None
    return {"access_token": token, "token_type": "bearer", "expires_in": SESSION_SECONDS}


@router.get("/me")
def get_current_demo_user(response: Response, identity: tuple[dict, str] = Depends(require_demo_identity)):
    """Return UI hints only; every business API must still check permissions."""
    response.headers["Cache-Control"] = "no-store"
    user, surface = identity
    return {
        "id": user["id"],
        "role": user["role"],
        "surface": surface,
        "experts": user["experts"],
        "modules": user["module_licenses"],
        "permissions": user["permissions"],
    }