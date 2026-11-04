
"""Private chat document storage and bounded text extraction; no publishing."""
import json
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from fastapi import HTTPException

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_BYTES = 2*1024*1024
_slots = threading.BoundedSemaphore(2)
SCHEMA = """CREATE TABLE IF NOT EXISTS chat_attachment(
 message_id TEXT PRIMARY KEY REFERENCES chat_message(id) ON DELETE CASCADE,
 filename TEXT NOT NULL, media_type TEXT NOT NULL, content BLOB NOT NULL
)"""

def fail(status, message):
    raise HTTPException(status, message, headers={"Cache-Control": "no-store"})

def upload(raw, media_type, filename):
    if not isinstance(filename, str) or not 1 <= len(filename) <= 120 or filename != filename.strip() or any(c in filename for c in '/\\') or any(ord(c) < 32 or ord(c) == 127 for c in filename):
        fail(422, "Use a filename of 1-120 characters without path separators.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".doc":
        fail(415, "Save the older .doc file as Word Document (.docx), then attach it.")
    expected = {".pdf": PDF, ".docx": DOCX}.get(suffix)
    if expected is None or expected != media_type:
        fail(415, "Attach one PDF or .docx Word document.")
    if not raw or len(raw) > MAX_BYTES:
        fail(413, "Use a nonempty document up to 2 MiB.")
    if not raw.startswith(b"%PDF-" if suffix == ".pdf" else b"PK\x03\x04"):
        fail(422, "File contents do not match the document type.")
    return {"filename": filename, "media_type": media_type, "content": raw}

def text(document):
    if not _slots.acquire(blocking=False):
        fail(429, "Document readers are busy. Please retry shortly.")
    try:
        worker = Path(__file__).with_name("file_worker.py")
        env = {k: v for k, v in os.environ.items() if not re.search(r"KEY|SECRET|TOKEN|PIN|PASSWORD|LICENSE|SECURITY_CONFIG", k, re.I)}
        try:
            dependency = importlib.util.find_spec("pypdf")
            if dependency is None:
                fail(503, "Document reader dependency is missing. Install backend requirements.")
            bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')"
            result = subprocess.run([sys.executable, "-I", "-c", bootstrap, str(Path(dependency.origin).parent.parent), str(worker), "pdf" if document["media_type"] == PDF else "docx"],
                input=document["content"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=18, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            fail(422, "Document reading timed out. Attach a smaller document.")
        if result.returncode or len(result.stdout) > 300000:
            fail(422, "Document exceeds safe reading limits. Attach a smaller document.")
        try:
            value = json.loads(result.stdout)
        except (ValueError, UnicodeError):
            fail(422, "Document could not be read.")
        if value.get("error"):
            fail(422, value["error"])
        value = value.get("text")
        if not isinstance(value, str) or not 5 <= len(value) <= 40000:
            fail(422, "No readable document text was found.")
        return value
    finally:
        _slots.release()

def metadata(db, message_id, conversation_id):
    row = db.execute("SELECT filename,media_type,length(content) AS size FROM chat_attachment WHERE message_id=?", (message_id,)).fetchone()
    return dict(row) | {"message_id": message_id, "conversation_id": conversation_id} if row else None

def save(db, context, message_id, document):
    from spia.services import chat_history as h
    upload(document["content"], document["media_type"], document["filename"])
    used = db.execute("SELECT COALESCE(SUM(length(a.content)),0) FROM chat_attachment a JOIN chat_message m ON m.id=a.message_id JOIN chat_master c ON c.id=m.conversation_id WHERE c.company_id=? AND c.installation_id=?", h.owner(context)[:2]).fetchone()[0]
    if used + len(document["content"]) > h.limit("SPIA_MAX_DOCUMENT_STORAGE_MIB", 500)*1024*1024:
        fail(409, "Document storage limit reached. Delete older conversations containing documents.")
    db.execute("INSERT INTO chat_attachment VALUES(?,?,?,?)", (message_id, document["filename"], document["media_type"], document["content"]))

def copy(db, context, old_id, new_id):
    row = db.execute("SELECT * FROM chat_attachment WHERE message_id=?", (old_id,)).fetchone()
    if row:
        save(db, context, new_id, dict(row))

def download(context, conversation_id, message_id):
    from spia.services import chat_history as h
    with h.connection() as db:
        row = h.row_for(db, context, conversation_id)
        h.authorize(context, row)
        value = db.execute("SELECT a.* FROM chat_attachment a JOIN chat_message m ON m.id=a.message_id WHERE m.conversation_id=? AND m.id=? AND m.role='user'", (conversation_id, h.identifier(message_id))).fetchone()
        if value is None:
            fail(404, "Attachment not found")
        h.authorize(context, row)
        return dict(value)
