"""Per-user expert request limits with a shared Redis option."""
import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import httpx
from fastapi import HTTPException

PREFIX = "/api/v1/experts/"
ROUTES = {
    "support", "implementation", "project-knowledge", "transcribe",
    "translate", "image-question", "document-question",
}

REDIS_LIMIT = """
local n = tonumber(redis.call('GET', KEYS[1]) or '0')
if n >= tonumber(ARGV[1]) then return 0 end
n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], 120) end
return 1
"""


def redis_allow(identity, window, limit):
    url = os.environ["UPSTASH_REDIS_REST_URL"].strip()
    token = os.environ["UPSTASH_REDIS_REST_TOKEN"].strip()
    if not url.startswith("https://") or not token:
        raise ValueError("Missing Redis configuration")

    digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    key = f"spia:expert-usage:v1:{digest}:{window}"
    response = httpx.post(
        url.rstrip("/") + "/",
        headers={"Authorization": f"Bearer {token}"},
        json=["EVAL", REDIS_LIMIT, "1", key, str(limit)],
        timeout=4.0,
        follow_redirects=False,
    )
    response.raise_for_status()

    data = response.json()
    result = data.get("result") if isinstance(data, dict) else None
    if type(result) is not int or result not in (0, 1):
        raise ValueError("Invalid Redis response")
    return result == 1


def sqlite_allow(identity, window, limit):
    location = Path(os.getenv("SPIA_USAGE_DB", ""))
    if not location.is_absolute():
        raise ValueError("SPIA_USAGE_DB must be an absolute path")

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
        """, (*identity, window, limit))
        return result.rowcount == 1


def enforce_expert_limit(method, path, identity):
    if method != "POST" or not path.startswith(PREFIX):
        return
    if path.removeprefix(PREFIX).rstrip("/") not in ROUTES:
        return

    headers = {"Cache-Control": "no-store"}
    try:
        limit = int(os.getenv("SPIA_EXPERT_REQUESTS_PER_MINUTE", "0"))
        if not 0 <= limit <= 10000:
            raise ValueError("Invalid request limit")
        if limit == 0:
            return

        now = int(time.time())
        user = (identity.company_id, identity.installation_id, identity.user_id)
        store = os.getenv("SPIA_USAGE_STORE", "sqlite")

        if store == "redis":
            allowed = redis_allow(user, now // 60, limit)
        elif store == "sqlite" and os.getenv("VERCEL") != "1":
            allowed = sqlite_allow(user, now // 60, limit)
        else:
            raise ValueError("Invalid usage store for this deployment")

    except (KeyError, ValueError, OSError, sqlite3.Error, httpx.HTTPError):
        raise HTTPException(
            503, "Expert usage limits are unavailable", headers=headers
        ) from None

    if not allowed:
        headers["Retry-After"] = str(60 - now % 60)
        raise HTTPException(
            429, "Expert request limit reached. Try again shortly.", headers=headers
        )