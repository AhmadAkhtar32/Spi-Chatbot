"""Per-user limits for expert requests on the company server."""
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from fastapi import HTTPException

EXPERT_ROUTES = {
    "/support", "/implementation", "/project-knowledge",
    "/transcribe", "/translate", "/image-question", "/document-question",
}


def enforce_expert_limit(method, path, identity):
    route = path.rstrip("/").removeprefix("/api/v1/experts")
    if method != "POST" or route not in EXPERT_ROUTES:
        return

    headers = {"Cache-Control": "no-store"}
    try:
        limit = int(os.getenv("SPIA_EXPERT_REQUESTS_PER_MINUTE", "0"))
        if not 0 <= limit <= 10000:
            raise ValueError()
        if limit == 0:
            return

        location = Path(os.getenv("SPIA_USAGE_DB", ""))
        if not location.is_absolute():
            raise ValueError()

        now = int(time.time())
        window = now // 60

        with closing(sqlite3.connect(location, timeout=3)) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS expert_usage (
                    company TEXT NOT NULL,
                    installation TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    window INTEGER NOT NULL,
                    hits INTEGER NOT NULL,
                    PRIMARY KEY (company, installation, user_id)
                )
            """)
            result = db.execute("""
                INSERT INTO expert_usage VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(company, installation, user_id) DO UPDATE SET
                    hits = CASE WHEN window = excluded.window THEN hits + 1 ELSE 1 END,
                    window = excluded.window
                WHERE window <> excluded.window OR hits < ?
            """, (identity.company_id, identity.installation_id,
                  identity.user_id, window, limit))
            allowed = result.rowcount == 1

    except (ValueError, OSError, sqlite3.Error) as exc:
        raise HTTPException(
            503, "Expert usage limits are unavailable", headers=headers
        ) from exc

    if not allowed:
        headers["Retry-After"] = str(60 - now % 60)
        raise HTTPException(
            429, "Expert request limit reached. Try again shortly.", headers=headers
        )