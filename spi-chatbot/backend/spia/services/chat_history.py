"""Installation-local history. Accept assistant answers from server code only."""
import base64
import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
from fastapi import HTTPException
from spia.security.access_control import AccessDenied
from spia.security.store import load_policy


def fail(status, message):
    raise HTTPException(status, message, headers={"Cache-Control": "no-store"})


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def canonical(value):
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return sorted((canonical(v) for v in value), key=encode)
    return value


def identifier(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        fail(422, "Use a canonical UUID")
    return value


def enabled():
    return not os.environ.get("VERCEL") and os.environ.get("SPIA_ENABLE_CHAT_HISTORY", "1") == "1"


def limit(name, default):
    try:
        number = int(os.environ.get(name, default))
        if not 1 <= number <= 10000:
            raise ValueError()
        return number
    except (TypeError, ValueError):
        fail(503, "Invalid history limit configuration")


def database_path():
    if not enabled():
        fail(503, "Persistent history requires the local/company-hosted application")
    chosen = os.environ.get("SPIA_DATA_DIR")
    if chosen:
        root = Path(chosen).expanduser()
        if not root.is_absolute():
            fail(503, "SPIA_DATA_DIR must be absolute")
    elif os.environ.get("LOCALAPPDATA"):
        root = Path(os.environ["LOCALAPPDATA"]) / "SPIA-Assistant/data"
    else:
        root = Path.home() / ".local/share/SPIA-Assistant/data"
    from spia.core.paths import BACKEND_DIR
    if root.resolve().is_relative_to(BACKEND_DIR.parent.parent.resolve()):
        fail(503, "Keep the history data directory outside application code")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root / "assistant.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_master (
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL, installation_id TEXT NOT NULL,
 user_id TEXT NOT NULL, title TEXT NOT NULL, scope TEXT NOT NULL, guard TEXT NOT NULL,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, deleted_at INTEGER,
 revision INTEGER NOT NULL DEFAULT 1, next_turn INTEGER NOT NULL DEFAULT 0,
 parent_id TEXT, parent_message_id TEXT
);
CREATE INDEX IF NOT EXISTS chat_owner ON chat_master
 (company_id,installation_id,user_id,updated_at DESC,id DESC);
CREATE TABLE IF NOT EXISTS chat_message (
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL
 REFERENCES chat_master(id) ON DELETE CASCADE,
 sequence INTEGER NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','assistant')),
 content TEXT NOT NULL, payload TEXT, image BLOB, created_at INTEGER NOT NULL,
 UNIQUE(conversation_id,sequence)
);
CREATE INDEX IF NOT EXISTS chat_message_order ON chat_message(conversation_id,sequence);
CREATE TABLE IF NOT EXISTS chat_request (
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL
 REFERENCES chat_master(id) ON DELETE CASCADE,
 turn INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','done','failed')),
 fingerprint TEXT NOT NULL, response TEXT, created_at INTEGER NOT NULL,
 UNIQUE(conversation_id,turn)
);
PRAGMA user_version=1;
"""


@contextmanager
def connection(write=False):
    path = database_path()
    db = sqlite3.connect(path, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            fail(503, "Unsupported history database version")
        if version == 0:
            db.executescript(SCHEMA)
        if os.name != "nt":
            path.chmod(0o600)
        if write:
            db.execute("BEGIN IMMEDIATE")
        yield db
        if write:
            db.commit()
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


def owner(context):
    value = context.identity
    return value.company_id, value.installation_id, value.user_id


def guard(context, scope):
    if scope == {"view": "business"}:
        kind = "business"
    elif scope == {"view": "company"}:
        kind = "company"
    elif (set(scope) == {"view", "expert", "module"}
          and scope["view"] == "knowledge"
          and scope["expert"] in {"support", "implementation"}
          and scope["module"] in {"financial", "inventory", "payroll"}):
        kind = "knowledge"
    else:
        fail(422, "Invalid conversation scope")
    policy = load_policy(context.identity)
    current = replace(context, policy=policy)
    grants = policy.model_dump(mode="json", include={"enabled", "channels", "assigned_pairs", "rules"})
    proof, view = {"grants": canonical(grants)}, None
    if kind == "business":
        from spia.services.business import BusinessService, MODULES
        service, pairs = BusinessService(current), set()
        for name in MODULES:
            try:
                service.require(name)
                pairs.update(service.used)
            except AccessDenied:
                continue
        if not pairs:
            raise AccessDenied("DATA_ACCESS_DENIED")
        proof["pairs"] = sorted(pairs)
    else:
        from spia.services.knowledge_access import KnowledgeAccess, UploadedKnowledgeAccess
        view = (UploadedKnowledgeAccess(current) if kind == "company"
                else KnowledgeAccess(current, scope["expert"], scope["module"]))
        proof["knowledge"] = [view.catalogue_version, view.knowledge.version, sorted(view.sources)]
    return hashlib.sha256(encode(proof).encode()).hexdigest(), view


def row_for(db, context, conversation_id, include_deleted=False):
    row = db.execute(
        "SELECT * FROM chat_master WHERE id=? AND company_id=? AND installation_id=? AND user_id=?"
        + ("" if include_deleted else " AND deleted_at IS NULL"),
        (identifier(conversation_id), *owner(context)),
    ).fetchone()
    if row is None:
        fail(404, "Conversation not found")
    return row


def authorize(context, row):
    proof, view = guard(context, json.loads(row["scope"]))
    if proof != row["guard"]:
        fail(403, "Access or approved knowledge changed. Start a new conversation.")
    return view


def summary(row):
    return {k: row[k] for k in ("id", "title", "created_at", "updated_at", "revision")} | {
        "scope": json.loads(row["scope"]),
        "restricted": bool(row["restricted"]) if "restricted" in row.keys() else False,
    }


def _insert(db, context, conversation_id, scope, proof, title):
    count = db.execute("SELECT count(*) FROM chat_master WHERE company_id=? AND installation_id=? AND user_id=? AND deleted_at IS NULL", owner(context)).fetchone()[0]
    if count >= limit("SPIA_MAX_CHATS_PER_USER", 100):
        fail(409, "Conversation limit reached. Export or delete an older conversation.")
    now = int(time.time()*1000)
    db.execute("INSERT INTO chat_master(id,company_id,installation_id,user_id,title,scope,guard,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
               (conversation_id, *owner(context), title, encode(scope), proof, now, now))


def create(context, conversation_id, scope, title="New chat"):
    identifier(conversation_id)
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
        fail(422, "Enter a title of 1 to 120 characters")
    proof, _ = guard(context, scope)
    with connection(write=True) as db:
        if db.execute("SELECT 1 FROM chat_master WHERE id=?", (conversation_id,)).fetchone():
            row = row_for(db, context, conversation_id)
            if row["scope"] != encode(scope):
                fail(409, "Conversation context cannot be changed")
            authorize(context, row)
        else:
            _insert(db, context, conversation_id, scope, proof, title.strip())
        return summary(row_for(db, context, conversation_id))


def listing(context, query="", before=None, page_size=20):
    if not isinstance(query, str) or len(query) > 120 or not 1 <= page_size <= 50:
        fail(422, "Invalid history search or page")
    with connection() as db:
        sql = "SELECT * FROM chat_master WHERE company_id=? AND installation_id=? AND user_id=? AND deleted_at IS NULL"
        args = [*owner(context)]
        if before:
            sql += " AND (updated_at<? OR (updated_at=? AND id<?))"
            args += [before[0], before[0], identifier(before[1])]
        rows = db.execute(sql+" ORDER BY updated_at DESC,id DESC LIMIT 10001", args).fetchall()
        found = []
        for row in rows:
            try:
                authorize(context, row)
            except (AccessDenied, HTTPException):
                if query:
                    continue
                row = dict(row) | {"title": "Unavailable conversation", "scope": "null", "restricted": True}
            if query:
                texts = [row["title"]] + [r[0] for r in db.execute("SELECT content FROM chat_message WHERE conversation_id=?", (row["id"],))]
                if not any(query.casefold() in text.casefold() for text in texts):
                    continue
            found.append(row)
            if len(found) > page_size:
                break
        items = found[:page_size]
        cursor = [items[-1]["updated_at"], items[-1]["id"]] if len(found) > page_size else None
        return {"conversations": [summary(r) for r in items], "next_cursor": cursor}


def messages(context, conversation_id, after=-1, page_size=50, *, before=None):
    if not 1 <= page_size <= 100 or not -1 <= after <= 2147483647 or (before is not None and (not 0 <= before <= 2147483647 or after != -1)):
        fail(422, "Invalid message page")
    with connection() as db:
        row = row_for(db, context, conversation_id)
        view = authorize(context, row)
        sql, cursor = ("sequence>? ORDER BY sequence", after) if before is None else ("sequence<? ORDER BY sequence DESC", before)
        rows = db.execute("SELECT * FROM chat_message WHERE conversation_id=? AND "+sql+" LIMIT ?", (conversation_id, cursor, page_size+1)).fetchall()
        visible = rows[:page_size] if before is None else list(reversed(rows[:page_size]))
        data = []
        for msg in visible:
            item = {k: msg[k] for k in ("id", "role", "content", "sequence", "created_at")}
            if msg["payload"]:
                payload = json.loads(msg["payload"])
                if view is not None and "reply" in payload:
                    from spia.api.experts import document_reply
                    scope = json.loads(row["scope"])
                    metadata = {k: payload[k] for k in ("history_source", "history_error", "clarification") if k in payload}
                    saved_escalation = payload.get("escalation")
                    payload = document_reply(context, view, scope.get("expert", "project_knowledge"), scope.get("module", "project"), payload["reply"], payload.get("sources", []), payload.get("language", "en"))
                    payload.update(metadata)
                    if saved_escalation is not None:
                        payload["escalation"] = saved_escalation
                    if scope["view"] == "company":
                        payload["source_labels"] = view.labels
                item["payload"] = payload
            if msg["image"]:
                item["image_base64"] = base64.b64encode(msg["image"]).decode()
            data.append(item)
        authorize(context, row)
        return {"conversation": summary(row), "messages": data,
                "next_after": data[-1]["sequence"] if before is None and len(rows) > page_size else None,
                "next_before": data[0]["sequence"] if before is not None and len(rows) > page_size else None}


def rename(context, conversation_id, title, revision):
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
        fail(422, "Enter a title of 1 to 120 characters")
    with connection(write=True) as db:
        row = row_for(db, context, conversation_id)
        authorize(context, row)
        if row["revision"] != revision:
            fail(409, "Conversation changed. Refresh and try again.")
        db.execute("UPDATE chat_master SET title=?,updated_at=?,revision=revision+1 WHERE id=?", (title.strip(), int(time.time()*1000), conversation_id))
        return summary(row_for(db, context, conversation_id))


def delete(context, conversation_id):
    with connection(write=True) as db:
        row = row_for(db, context, conversation_id, True)
        now = int(time.time()*1000)
        db.execute("UPDATE chat_master SET deleted_at=COALESCE(deleted_at,?),updated_at=?,revision=revision+1 WHERE id=?", (now, now, row["id"]))


def fork(context, conversation_id, message_id, title="Edited question"):
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
        fail(422, "Enter a title of 1 to 120 characters")
    with connection(write=True) as db:
        row = row_for(db, context, conversation_id)
        authorize(context, row)
        msg = db.execute("SELECT * FROM chat_message WHERE conversation_id=? AND id=? AND role='user'", (conversation_id, identifier(message_id))).fetchone()
        if msg is None:
            fail(404, "Question not found")
        if db.execute("SELECT 1 FROM chat_request WHERE conversation_id=? AND state='pending'", (conversation_id,)).fetchone():
            fail(409, "Wait for the active answer before editing")
        earlier = db.execute("SELECT * FROM chat_message WHERE conversation_id=? AND sequence<? ORDER BY sequence", (conversation_id, msg["sequence"])).fetchall()
        answer = db.execute("SELECT payload FROM chat_message WHERE conversation_id=? AND sequence=?", (conversation_id, msg["sequence"]+1)).fetchone()
        hint = json.loads(answer[0]).get("history_source") if answer and answer[0] else None
        new_id = str(uuid.uuid4())
        _insert(db, context, new_id, json.loads(row["scope"]), row["guard"], title.strip())
        for n, old in enumerate(earlier):
            db.execute("INSERT INTO chat_message VALUES(?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), new_id, n, old["role"], old["content"], old["payload"], old["image"], old["created_at"]))
        db.execute("UPDATE chat_master SET next_turn=?,parent_id=?,parent_message_id=? WHERE id=?", (len(earlier)//2, conversation_id, message_id, new_id))
        return {"conversation": summary(row_for(db, context, new_id)), "draft": msg["content"],
                "image_base64": base64.b64encode(msg["image"]).decode() if msg["image"] else None, "source": hint}


def claim(context, conversation_id, request_id, fingerprint):
    identifier(request_id)
    with connection(write=True) as db:
        row = row_for(db, context, conversation_id)
        authorize(context, row)
        previous = db.execute("SELECT * FROM chat_request WHERE id=?", (request_id,)).fetchone()
        if previous:
            if previous["conversation_id"] != conversation_id or previous["fingerprint"] != fingerprint:
                fail(409, "Request ID was already used for different input")
            if previous["state"] == "done":
                return row, json.loads(previous["response"])
            fail(409, "Request is running or was interrupted. Refresh before retrying.")
        count = db.execute("SELECT count(*) FROM chat_message WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
        pending = db.execute("SELECT count(*) FROM chat_request WHERE conversation_id=? AND state='pending'", (conversation_id,)).fetchone()[0]
        if count + 2*pending + 2 > limit("SPIA_MAX_MESSAGES_PER_CHAT", 500):
            fail(409, "Message limit reached. Start a continuation conversation.")
        db.execute("INSERT INTO chat_request VALUES(?,?,?,'pending',?,NULL,?)", (request_id, conversation_id, row["next_turn"], fingerprint, int(time.time()*1000)))
        db.execute("UPDATE chat_master SET next_turn=next_turn+1 WHERE id=?", (conversation_id,))
        return row, None


def finish(context, conversation_id, request_id, question, payload, image=None, http_status=200):
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        fail(422, "Enter a question of 1 to 2000 characters")
    if not isinstance(payload, dict) or not ("reply" in payload or "kind" in payload):
        fail(422, "Invalid server response")
    with connection(write=True) as db:
        row = row_for(db, context, conversation_id)
        authorize(context, row)
        request = db.execute("SELECT * FROM chat_request WHERE id=? AND conversation_id=? AND state='pending'", (identifier(request_id), conversation_id)).fetchone()
        if request is None:
            fail(409, "Pending history request is unavailable")
        now, user_id, answer_id = int(time.time()*1000), str(uuid.uuid4()), str(uuid.uuid4())
        result = dict(payload)
        result["history"] = {"conversation_id": conversation_id, "user_message_id": user_id,
                             "answer_message_id": answer_id, "user_sequence": request["turn"]*2,
                             "answer_sequence": request["turn"]*2+1, "revision": row["revision"]+1}
        db.execute("INSERT INTO chat_message VALUES(?,?,?,?,?,?,?,?)", (user_id, conversation_id, request["turn"]*2, "user", question.strip(), None, image, request["created_at"]))
        db.execute("INSERT INTO chat_message VALUES(?,?,?,?,?,?,?,?)", (answer_id, conversation_id, request["turn"]*2+1, "assistant", payload.get("reply") or encode(payload), encode(payload), None, now))
        title = " ".join(question.split())[:80] if row["title"] == "New chat" else row["title"]
        db.execute("UPDATE chat_master SET title=?,updated_at=?,revision=revision+1 WHERE id=?", (title, now, conversation_id))
        db.execute("UPDATE chat_request SET state='done',response=? WHERE id=?", (encode({"status": http_status, "body": result}), request_id))
        return result


def abandon(request_id):
    with connection(write=True) as db:
        db.execute("UPDATE chat_request SET state='failed' WHERE id=? AND state='pending'", (identifier(request_id),))


def backup(destination):
    destination = Path(destination).expanduser().resolve()
    if destination == database_path().resolve() or destination.exists():
        raise ValueError("Choose a new backup file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with connection() as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination
