"""Create internal software bug reports on the company server."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from spia.api.access import active_pairs, require_access_context
from spia.services import chat_history
from spia.services.bug_tickets import create_bug_ticket
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from typing import Annotated
from fastapi import Path as ApiPath

from fastapi import Query


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
    
@router.get("/api/v1/bug-reports")
def bug_report_availability(
    response: Response,
    context=Depends(require_access_context),
):
    response.headers["Cache-Control"] = "no-store"
    return {
        "available": chat_history.enabled() and any(
            pair["feature"] in _ALLOWED_FEATURES
            for pair in active_pairs(context)
        )
    }
    
TicketStatus = Literal["open", "in_progress", "resolved"]
TicketReference = Annotated[str, ApiPath(pattern=r"^BUG-[0-9A-F]{32}$")]


class BugReportStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_status: TicketStatus
    status: TicketStatus


def require_bug_queue_access(
    context=Depends(require_access_context),
):
    headers = {"Cache-Control": "no-store"}

    if not any(
        pair["feature"] == "implementation_expert"
        for pair in active_pairs(context)
    ):
        raise HTTPException(
            status_code=403,
            detail="Active Implementation access is required to manage bug reports.",
            headers=headers,
        )

    if not chat_history.enabled():
        raise HTTPException(
            status_code=503,
            detail="The bug-report queue is available on the local or company-hosted application.",
            headers=headers,
        )

    return context.identity


@contextmanager
def _bug_queue_connection(*, write=False):
    try:
        path = Path(chat_history.database_path())
        if not path.is_absolute() or not path.is_file():
            raise ValueError("Existing SQLite database required.")

        mode = "rw" if write else "ro"
        with closing(sqlite3.connect(
            f"{path.as_uri()}?mode={mode}", uri=True, timeout=5
        )) as db:
            db.row_factory = sqlite3.Row
            with db:
                yield db
    except (OSError, ValueError, sqlite3.Error):
        raise HTTPException(
            status_code=503,
            detail="Bug report storage is unavailable.",
            headers={"Cache-Control": "no-store"},
        ) from None


@router.get("/api/v1/bug-reports/queue")
def list_bug_reports(
    response: Response,
    reference: str | None = Query(
        default=None, pattern=r"^BUG-[0-9A-F]{32}$"
    ),
    status: TicketStatus | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    identity=Depends(require_bug_queue_access),
):
    response.headers["Cache-Control"] = "no-store"

    where = ["company_id = ?", "installation_id = ?"]
    params = [identity.company_id, identity.installation_id]

    if reference is not None:
        where.append("reference = ?")
        params.append(reference)
    if status is not None:
        where.append("status = ?")
        params.append(status)

    with _bug_queue_connection() as db:
        table_exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'spia_bug_ticket'"
        ).fetchone()
        if not table_exists:
            return {"items": [], "next_offset": None}

        rows = db.execute(
            "SELECT reference, summary, status, created_by, created_at "
            "FROM spia_bug_ticket WHERE " + " AND ".join(where) +
            " ORDER BY created_at DESC, reference DESC LIMIT ? OFFSET ?",
            (*params, limit + 1, offset),
        ).fetchall()

    return {
        "items": [dict(row) for row in rows[:limit]],
        "next_offset": offset + limit if len(rows) > limit else None,
    }


@router.patch("/api/v1/bug-reports/queue/{reference}")
def update_bug_report_status(
    reference: TicketReference,
    body: BugReportStatusRequest,
    response: Response,
    identity=Depends(require_bug_queue_access),
):
    headers = {"Cache-Control": "no-store"}
    next_status = {"open": "in_progress", "in_progress": "resolved"}

    if next_status.get(body.expected_status) != body.status:
        raise HTTPException(
            status_code=409,
            detail="Use Open → In progress → Resolved.",
            headers=headers,
        )

    changed_at = datetime.now(timezone.utc).isoformat()
    scope = (reference, identity.company_id, identity.installation_id)

    with _bug_queue_connection(write=True) as db:
        db.execute("BEGIN IMMEDIATE")
        table_exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'spia_bug_ticket'"
        ).fetchone()
        if not table_exists:
            raise HTTPException(404, "Bug report not found.", headers=headers)

        changed = db.execute(
            "UPDATE spia_bug_ticket SET status = ? "
            "WHERE reference = ? AND company_id = ? "
            "AND installation_id = ? AND status = ?",
            (body.status, *scope, body.expected_status),
        )

        if changed.rowcount != 1:
            row = db.execute(
                "SELECT status FROM spia_bug_ticket "
                "WHERE reference = ? AND company_id = ? AND installation_id = ?",
                scope,
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Bug report not found.", headers=headers)
            raise HTTPException(
                409, "Ticket status changed. Refresh and try again.", headers=headers
            )

        db.execute("""
            CREATE TABLE IF NOT EXISTS spia_bug_ticket_status_log (
                id INTEGER PRIMARY KEY,
                reference TEXT NOT NULL,
                company_id TEXT NOT NULL,
                installation_id TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                changed_at TEXT NOT NULL
            )
        """)
        db.execute("""
            INSERT INTO spia_bug_ticket_status_log (
                reference, company_id, installation_id, changed_by,
                previous_status, new_status, changed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (*scope, identity.user_id, body.expected_status, body.status, changed_at))

    response.headers.update(headers)
    return {
        "reference": reference,
        "status": body.status,
        "changed_at": changed_at,
    }