"""History storage checks. Fictional licenses and users; no AI/provider calls."""
import base64
import json
import os
import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from spia.api.access import context_for_token
from spia.core.paths import BACKEND_DIR
from spia.security.access_control import AccessDenied
from spia.security.presenter_sessions import issue_presenter_session
from spia.services import chat_history as h
from spia.tools.setup_security import prepare


class HistoryStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="spia-history-storage-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        prepare(BACKEND_DIR / "data/sample_data.json", self.root / "security",
                self.root / "issuer.pem", "SPIA-INTERNAL", "SPIA-DEV-01", 30,
                b"fictional-history-test-password")
        catalogue = self.root / "catalogue.json"
        catalogue.write_bytes((BACKEND_DIR / "data/knowledge_access.json").read_bytes())
        environment = patch.dict(os.environ, {
            "SPIA_SECURITY_DIR": str(self.root / "security"),
            "SPIA_DATA_DIR": str(self.root / "data"),
            "SPIA_ENABLE_CHAT_HISTORY": "1",
            "SPIA_MAX_CHATS_PER_USER": "100",
            "SPIA_MAX_MESSAGES_PER_CHAT": "500",
            "SPIA_KNOWLEDGE_ACCESS_FILE": str(catalogue),
            "ENABLE_INTERNAL_SESSIONS": "1",
            "PRESENTER_SESSION_SECRET": "fictional-history-session-secret-" * 3,
            "PRESENTER_SPIA_PIN": "fictional-history-pin-1234",
            "PRESENTER_MOBILE_PIN": "fictional-mobile-pin-5678",
        })
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("SPIA_SECURITY_CONFIG_B64", None)
        os.environ.pop("VERCEL", None)
        self.user = self.login("demo_operations")
        self.other = self.login("demo_employee")

    def login(self, user):
        token = issue_presenter_session(user, "spia_tsplus", os.environ["PRESENTER_SPIA_PIN"])
        return context_for_token(token)

    def create(self, scope=None, context=None):
        cid = str(uuid.uuid4())
        h.create(context or self.user, cid, scope or {"view": "business"})
        return cid

    def turn(self, cid, question="Show SO-1001", context=None, **kwargs):
        context = context or self.user
        rid = str(uuid.uuid4())
        h.claim(context, cid, rid, "fingerprint-" + rid)
        return h.finish(context, cid, rid, question,
                        {"reply": "Authorised fictional response", "sources": [], "language": "en"}, **kwargs)

    def denied(self, status, operation):
        with self.assertRaises(HTTPException) as caught:
            operation()
        self.assertEqual(caught.exception.status_code, status)

    def test_schema_and_persistence(self):
        cid = self.create()
        self.turn(cid)
        self.assertEqual(len(h.messages(self.login("demo_operations"), cid)["messages"]), 2)
        with h.connection() as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(h.database_path(), self.root / "data/assistant.db")

    def test_cross_user_and_company_access(self):
        cid = self.create()
        self.turn(cid)
        self.denied(404, lambda: h.messages(self.other, cid))
        self.denied(404, lambda: h.delete(self.other, cid))
        foreign = replace(self.user, identity=self.user.identity.model_copy(update={"company_id": "OTHER-COMPANY"}))
        self.denied(404, lambda: h.messages(foreign, cid))

    def test_scope_and_identifier_validation(self):
        self.denied(422, lambda: h.create(self.user, str(uuid.uuid4()), {"view": "business", "user_id": "someone-else"}))
        self.denied(422, lambda: h.create(self.user, "invalid-id", {"view": "business"}))
        cid = self.create()
        with self.assertRaises((HTTPException, AccessDenied)):
            h.create(self.user, cid, {"view": "company"})
        self.assertEqual(h.messages(self.user, cid)["conversation"]["scope"], {"view": "business"})

    def test_search_rename_and_delete(self):
        cid = self.create()
        question = "\u0645\u06a9\u0626\u06cc \u06a9\u0627 \u0627\u0633\u0679\u0627\u06a9"
        self.turn(cid, question)
        revision = h.messages(self.user, cid)["conversation"]["revision"]
        h.rename(self.user, cid, "Stock discussion", revision)
        self.assertEqual(h.listing(self.user, question)["conversations"][0]["id"], cid)
        self.denied(409, lambda: h.rename(self.user, cid, "Stale edit", revision))
        h.delete(self.user, cid)
        self.denied(404, lambda: h.messages(self.user, cid))
        self.assertFalse(h.listing(self.user)["conversations"])

    def test_duplicate_and_interrupted_requests(self):
        cid, rid = self.create(), str(uuid.uuid4())
        h.claim(self.user, cid, rid, "same")
        self.denied(409, lambda: h.claim(self.user, cid, rid, "same"))
        result = h.finish(self.user, cid, rid, "Question", {"reply": "Answer"})
        _, previous = h.claim(self.user, cid, rid, "same")
        self.assertEqual(previous, {"status": 200, "body": result})
        self.denied(409, lambda: h.claim(self.user, cid, rid, "different"))
        failed = str(uuid.uuid4())
        h.claim(self.user, cid, failed, "failed")
        h.abandon(failed)
        self.denied(409, lambda: h.claim(self.user, cid, failed, "failed"))
        self.assertEqual(len(h.messages(self.user, cid)["messages"]), 2)

    def test_configurable_limits(self):
        cid = self.create()
        with patch.dict(os.environ, {"SPIA_MAX_MESSAGES_PER_CHAT": "2", "SPIA_MAX_CHATS_PER_USER": "1"}):
            self.turn(cid)
            self.denied(409, lambda: self.turn(cid))
            self.denied(409, lambda: self.create())

    def test_pagination_and_latest_page(self):
        cid = self.create()
        for n in range(4):
            receipt = self.turn(cid, "Question " + str(n))["history"]
            self.assertEqual(receipt["user_sequence"], n*2)
        page = h.messages(self.user, cid, page_size=3, before=2147483647)
        self.assertEqual([m["sequence"] for m in page["messages"]], [5, 6, 7])
        older = h.messages(self.user, cid, page_size=3, before=page["next_before"])
        self.assertEqual([m["sequence"] for m in older["messages"]], [2, 3, 4])
        first = h.messages(self.user, cid, page_size=1)
        self.assertEqual(first["messages"][0]["role"], "user")

    def test_edit_branch_preserves_original_and_image(self):
        cid = self.create()
        self.turn(cid, "First question")
        self.turn(cid, "Second question", image=b"fictional-sanitized-image")
        original = h.messages(self.user, cid)["messages"]
        branch = h.fork(self.user, cid, original[2]["id"])
        copied = h.messages(self.user, branch["conversation"]["id"])["messages"]
        self.assertEqual(branch["draft"], "Second question")
        self.assertEqual(base64.b64decode(branch["image_base64"]), b"fictional-sanitized-image")
        self.assertEqual(len(copied), 2)
        self.assertNotEqual(copied[0]["id"], original[0]["id"])
        self.assertIsNone(branch["source"])
        self.assertEqual(h.messages(self.user, cid)["messages"], original)

    def test_changed_authority_withholds_old_history(self):
        cid = self.create()
        self.turn(cid)
        path = self.root / "security/user_access.json"
        users = json.loads(path.read_text())
        for user in users:
            if user["user_id"] == "demo_operations":
                user["rules"] = [r for r in user["rules"] if r["module"] != "sales"]
                user["revision"] += 1
        path.write_text(json.dumps(users))
        self.denied(403, lambda: h.messages(self.user, cid))
        listed = h.listing(self.user)["conversations"][0]
        self.assertEqual(listed["title"], "Unavailable conversation")
        self.assertIsNone(listed["scope"])
        self.assertTrue(listed["restricted"])
        h.delete(self.user, cid)

    def test_package_and_module_expiry_and_renewal(self):
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from spia.security.license_policy import SIGNING_CONTEXT
        cid = self.create()
        self.turn(cid)
        path = self.root / "security/company_license.json"
        original = path.read_bytes()
        key = load_pem_private_key((self.root / "issuer.pem").read_bytes(), password=b"fictional-history-test-password")
        def issue(group, name, expired):
            envelope = json.loads(original)
            payload = json.loads(base64.urlsafe_b64decode(envelope["payload"]))
            for term in payload[group]:
                if term.get("feature", term.get("module")) == name:
                    term["starts_at"] = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
                    term["expires_at"] = (datetime.now(timezone.utc)+timedelta(days=-1 if expired else 60)).isoformat()
            raw = json.dumps(payload, separators=(",", ":")).encode()
            envelope["payload"] = base64.urlsafe_b64encode(raw).decode()
            envelope["signature"] = base64.urlsafe_b64encode(key.sign(SIGNING_CONTEXT+envelope["key_id"].encode()+b"\0"+raw)).decode()
            path.write_text(json.dumps(envelope))
        for group, name in (("modules", "sales"), ("packages", "business_lookup")):
            issue(group, name, True)
            with self.assertRaises((HTTPException, AccessDenied)):
                h.messages(self.user, cid)
            issue(group, name, False)
            self.assertEqual(len(h.messages(self.user, cid)["messages"]), 2)

    def test_knowledge_change_withholds_archived_answer(self):
        support = self.login("demo_support")
        cid = self.create({"view": "knowledge", "expert": "support", "module": "financial"}, support)
        self.turn(cid, context=support)
        catalogue = self.root / "catalogue.json"
        value = json.loads(catalogue.read_text())
        for source in value["sources"]:
            if source["expert"] == "support":
                source["status"] = "blocked"
        catalogue.write_text(json.dumps(value))
        with self.assertRaises(AccessDenied):
            h.messages(support, cid)

    def test_concurrent_short_writes(self):
        cid = self.create()
        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(lambda n: self.turn(cid, "Concurrent " + str(n)), range(16)))
        self.assertEqual(len(results), 16)
        messages = h.messages(self.user, cid)["messages"]
        self.assertEqual([m["sequence"] for m in messages], list(range(32)))
        self.assertEqual(len({m["id"] for m in messages}), 32)

    def test_deleted_chat_rejects_late_answer(self):
        cid, rid = self.create(), str(uuid.uuid4())
        h.claim(self.user, cid, rid, "pending")
        h.delete(self.user, cid)
        self.denied(404, lambda: h.finish(self.user, cid, rid, "Question", {"reply": "Late answer"}))
        with h.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chat_message").fetchone()[0], 0)

    def test_backup_and_serverless_guard(self):
        cid = self.create()
        self.turn(cid)
        target = h.backup(self.root / "backups/test.db")
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT count(*) FROM chat_message").fetchone()[0], 2)
        with self.assertRaises(ValueError):
            h.backup(target)
        with patch.dict(os.environ, {"VERCEL": "1"}):
            self.assertFalse(h.enabled())
            self.denied(503, h.database_path)


    def test_backup_closes_every_connection(self):
        real_connect, opened = sqlite3.connect, []
        def tracked_connect(*args, **kwargs):
            db = real_connect(*args, **kwargs)
            opened.append(db)
            return db
        try:
            with patch.object(h.sqlite3, "connect", side_effect=tracked_connect):
                h.backup(self.root / "backups/closed.db")
            self.assertEqual(len(opened), 2)
            for db in opened:
                with self.assertRaises(sqlite3.ProgrammingError):
                    db.execute("SELECT 1")
        finally:
            for db in opened:
                db.close()


if __name__ == "__main__":
    unittest.main()
