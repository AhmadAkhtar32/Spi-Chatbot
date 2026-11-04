"""Create internal software bug reports on the company server."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from spia.api.access import active_pairs, require_access_context
from spia.services import chat_history
from spia.services.bug_tickets import create_bug_ticket


router = APIRouter(tags=["Bug reports"])

_ALLOWED_FEATURES = frozenset({
    "support_expert",
    "implementation_expert",
})


class BugReportRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    summary: str = Field(min_length=1, max_length=500)


@router.post("/api/v1/bug-reports", status_code=201)
def report_bug(
    body: BugReportRequest,
    response: Response,
    context=Depends(require_access_context),
):
    headers = {"Cache-Control": "no-store"}

    if not any(
        pair["feature"] in _ALLOWED_FEATURES
        for pair in active_pairs(context)
    ):
        raise HTTPException(
            status_code=403,
            detail="An active Support or Implementation entitlement is required.",
            headers=headers,
        )

    if not chat_history.enabled():
        raise HTTPException(
            status_code=503,
            detail="Bug reports are available on the local or company-hosted application.",
            headers=headers,
        )

    identity = context.identity

    try:
        ticket = create_bug_ticket(
            chat_history.database_path(),
            company_id=identity.company_id,
            installation_id=identity.installation_id,
            created_by=identity.user_id,
            summary=body.summary,
        )
    except (OSError, ValueError, sqlite3.Error):
        raise HTTPException(
            status_code=503,
            detail="Bug report storage is unavailable. Try again or contact your administrator.",
            headers=headers,
        ) from None

    response.headers.update(headers)
    return {
        "reference": ticket["reference"],
        "status": ticket["status"],
        "created_at": ticket["created_at"],
    }