"""SQLite storage for internal software bug reports."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def create_bug_ticket(
    db_path: Path,
    *,
    company_id: str,
    installation_id: str,
    created_by: str,
    summary: str,
) -> dict:
    """Insert a ticket using scope and creator supplied by the backend."""
    if not all(
        isinstance(value, str) and value.strip()
        for value in (company_id, installation_id, created_by)
    ):
        raise ValueError("Company, installation and creator are required.")
    summary = summary.strip()
    if not 1 <= len(summary) <= 500:
        raise ValueError("Summary must contain 1 to 500 characters.")

    path = Path(db_path)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("An existing absolute SQLite path is required.")

    ticket = {
        "reference": f"BUG-{uuid4().hex.upper()}",
        "company_id": company_id,
        "installation_id": installation_id,
        "created_by": created_by,
        "summary": summary,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)) as db:
        with db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS spia_bug_ticket (
                    reference TEXT PRIMARY KEY NOT NULL,
                    company_id TEXT NOT NULL,
                    installation_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    summary TEXT NOT NULL CHECK(length(summary) BETWEEN 1 AND 500),
                    status TEXT NOT NULL CHECK(status IN ('open', 'in_progress', 'resolved')),
                    created_at TEXT NOT NULL
                )
            """)
            db.execute("""
                INSERT INTO spia_bug_ticket (
                    reference, company_id, installation_id, created_by,
                    summary, status, created_at
                ) VALUES (
                    :reference, :company_id, :installation_id, :created_by,
                    :summary, :status, :created_at
                )
            """, ticket)
    return ticket