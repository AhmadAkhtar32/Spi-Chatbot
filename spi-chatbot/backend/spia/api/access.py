"""License-aware routes with a temporary internal presenter-session adapter.

Client deployments must use verified, company-bound SPIA identity instead.
"""

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from fastapi import (
    APIRouter, Depends, Header, HTTPException, Request, Response,
)
from pydantic import BaseModel, ConfigDict, Field

from spia.security.access_control import (
    AccessDenied, Identity, Key, Policy, require_feature,
)
from spia.security.presenter_profiles import AccessDenied as SessionDenied
from spia.security.presenter_sessions import issue_presenter_session, verify_presenter_session
from spia.security.license_policy import UserAccess, resolve_policy
from spia.security.store import (
    SecurityConfigurationError, read_configuration,
)

router = APIRouter(tags=["Assistant access"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: Key
    surface: Literal["spia_tsplus", "mobile"]
    pin: str = Field(
        min_length=12,
        max_length=256,
        pattern=r"^[\x21-\x7e]+$",
    )


@dataclass(frozen=True)
class AccessContext:
    user: dict
    surface: str
    identity: Identity
    policy: Policy
    access: UserAccess


def fail(status, detail):
    headers = {"Cache-Control": "no-store"}

    if status == 401:
        headers["WWW-Authenticate"] = "Bearer"

    raise HTTPException(
        status,
        detail,
        headers=headers,
    )


def require_internal_sessions():
    if os.environ.get("ENABLE_INTERNAL_SESSIONS") != "1":
        fail(
            404,
            "Internal presentation sessions are disabled",
        )


def bearer_token(authorization):
    scheme, separator, token = (
        authorization or ""
    ).partition(" ")

    if (
        scheme.lower() != "bearer"
        or not separator
        or not token
        or " " in token
    ):
        fail(401, "A valid session is required")

    return token


def active_pairs(context):
    result = []

    pairs = sorted(
        context.policy.assigned_pairs,
        key=lambda pair: (pair.feature, pair.module),
    )

    for pair in pairs:
        try:
            require_feature(
                context.identity,
                context.policy,
                pair.feature,
                pair.module,
            )
        except AccessDenied:
            continue

        result.append({
            "feature": pair.feature,
            "module": pair.module,
        })

    return result


def context_for_token(token):
    require_internal_sessions()

    try:
        user, surface = verify_presenter_session(token)

        # Read claims only after signature verification succeeds.
        encoded = token.split(".")[0]
        decoded = base64.urlsafe_b64decode(
            encoded + "=" * (-len(encoded) % 4)
        )
        claims = json.loads(decoded)

        expires_at = datetime.fromtimestamp(
            claims["exp"],
            timezone.utc,
        )

    except SessionDenied:
        fail(401, "Invalid or expired session")

    except (
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
    ):
        fail(401, "Invalid session claims")

    except RuntimeError:
        fail(
            503,
            "Internal session settings are unavailable",
        )

    try:
        settings, keys, users, raw_license = (
            read_configuration()
        )

        access = users.get(user["id"])

        if access is None:
            raise AccessDenied("USER_NOT_CONFIGURED")

        identity = Identity(
            user_id=user["id"],
            company_id=settings.company_id,
            installation_id=settings.installation_id,
            channel=surface,
            expires_at=expires_at,
        )

        policy = resolve_policy(
            identity,
            raw_license,
            keys,
            access,
            minimum_revision=settings.minimum_revision,
        )

        context = AccessContext(
            user,
            surface,
            identity,
            policy,
            access,
        )

        if not active_pairs(context):
            raise AccessDenied("NO_ACTIVE_ACCESS")

        return context

    except SecurityConfigurationError:
        fail(
            503,
            "Assistant security configuration is unavailable",
        )

    except AccessDenied as exc:
        fail(403, exc.code)


def require_access_context(
    request: Request,
    authorization: str | None = Header(default=None),
):
    cached = getattr(
        request.state,
        "access_context",
        None,
    )

    if cached is not None:
        return cached

    return context_for_token(
        bearer_token(authorization)
    )


def require_identity(
    context: AccessContext = Depends(require_access_context),
):
    """Compatibility shape; record-level migration follows separately."""
    return context.user, context.surface


@router.post("/api/v1/session")
def create_session(
    body: LoginRequest,
    response: Response,
):
    require_internal_sessions()

    try:
        token = issue_presenter_session(
            body.user_id,
            body.surface,
            body.pin,
        )

    except SessionDenied:
        fail(401, "Invalid session credentials")

    except RuntimeError:
        fail(
            503,
            "Internal session settings are unavailable",
        )

    context = context_for_token(token)
    response.headers["Cache-Control"] = "no-store"

    remaining = int(
        (
            context.identity.expires_at
            - datetime.now(timezone.utc)
        ).total_seconds()
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": max(0, remaining),
    }


@router.get("/api/v1/me")
def current_user(
    response: Response,
    identity=Depends(require_identity),
):
    """Retain the existing UI response during frontend migration."""
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


@router.get("/api/v1/access")
def current_access(
    response: Response,
    context=Depends(require_access_context),
):
    """Fresh UI hints; per-record authorization remains mandatory."""
    response.headers["Cache-Control"] = "no-store"

    return {
        "user_id": context.identity.user_id,
        "company_id": context.identity.company_id,
        "installation_id": context.identity.installation_id,
        "channel": context.identity.channel,
        "roles": sorted(context.access.roles),
        "active_pairs": active_pairs(context),
        "access_revision": context.access.revision,
        "session_expires_at": context.identity.expires_at,
        "policy_valid_until": context.policy.valid_until,
    }