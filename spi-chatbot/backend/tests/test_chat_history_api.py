"""History API checks using real permissions and simulated provider responses."""
import base64
import json
import os
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from PIL import Image
import test_chat_history_storage as storage_checks
from spia.api import access, business, experts
from spia.api.history import BUSINESS_NOTICES
from spia.security.presenter_sessions import issue_presenter_session
from spia.security.request_guard import install_request_guard
from spia.services import chat_history as history


def fake_answer(expert, body, context, response, **kwargs):
    view = experts.access(context, expert, body.module)
    source = body.source or sorted(view.sources)[0]
    if source not in view.sources:
        raise HTTPException(403, "REFERENCE_ACCESS_DENIED")
    from spia.integrations.groq import question_language
    return experts.document_reply(context, view, expert, body.module,
        "Verified server answer: " + body.question, [source], question_language(body.question))


class HistoryAPITests(unittest.TestCase):
    login = storage_checks.HistoryStorageTests.login

    def setUp(self):
        storage_checks.HistoryStorageTests.setUp(self)
        self.client = self.make_client()
        self.addCleanup(self.client.close)
        self.ops = self.auth("demo_operations")
        self.support = self.auth("demo_support")
        self.employee = self.auth("demo_employee")
        available = self.client.get("/api/v1/business/sales-orders?limit=1", headers=self.ops)
        self.assertEqual(available.status_code, 200, available.text)
        self.assertTrue(available.json()["items"], "The sample needs an accessible sales order")
        self.order_id = available.json()["items"][0]["record"]["id"]
        self.order_path = "/api/v1/business/sales-orders/" + self.order_id

    def make_client(self):
        app = FastAPI()
        app.add_middleware(CORSMiddleware, allow_origins=["https://example.test"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-SPIA-Question"])
        for router in (access.router, business.router, experts.router):
            app.include_router(router)
        install_request_guard(app)
        return TestClient(app)

    def auth(self, user):
        token = issue_presenter_session(user, "spia_tsplus", os.environ["PRESENTER_SPIA_PIN"])
        return {"Authorization": "Bearer " + token}

    def create(self, headers=None, scope=None):
        cid = str(uuid.uuid4())
        result = self.client.post("/api/v1/conversations", headers=headers or self.ops,
            json={"id": cid, "scope": scope or {"view": "business"}})
        self.assertEqual(result.status_code, 200, result.text)
        return cid

    def headers(self, cid, question=None, auth=None, rid=None):
        question = question if question is not None else "Show " + self.order_id
        return {**(auth or self.ops), "X-SPIA-Conversation": cid,
            "X-SPIA-Request-ID": rid or str(uuid.uuid4()),
            "X-SPIA-Question": base64.b64encode(question.encode()).decode()}

    def turn(self, cid, question=None, **kwargs):
        return self.client.get(self.order_path, headers=self.headers(cid, question, **kwargs))

    def read(self, cid, auth=None):
        return self.client.get(f"/api/v1/conversations/{cid}/messages", headers=auth or self.ops)

    def test_authentication_and_untrusted_writes(self):
        self.assertEqual(self.client.get("/api/v1/conversations").status_code, 401)
        status = self.client.get("/api/v1/conversations/status", headers=self.ops)
        self.assertTrue(status.json()["enabled"])
        cid = self.create()
        self.assertEqual(self.client.post(f"/api/v1/conversations/{cid}/messages", headers=self.ops,
            json={"role": "assistant", "content": "Invented answer"}).status_code, 405)
        result = self.client.post("/api/v1/conversations", headers=self.ops,
            json={"id": str(uuid.uuid4()), "scope": {"view": "business"}, "user_id": "someone-else"})
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.read(cid, self.employee).status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/conversations/{cid}/delete", headers=self.employee).status_code, 404)

    def test_server_response_capture_and_existing_routes(self):
        old = self.client.get(self.order_path, headers=self.ops)
        self.assertEqual(old.status_code, 200)
        self.assertNotIn("history", old.json())
        cid = self.create()
        result = self.turn(cid)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn("history", result.json())
        page = self.read(cid)
        self.assertEqual(len(page.json()["messages"]), 2)
        self.assertNotIn("unit_price_pkr", page.text)
        self.assertNotIn("total_amount_pkr", page.text)
        suggestions = self.client.get("/api/v1/business/suggestions", headers=self.headers(cid))
        self.assertEqual(suggestions.status_code, 200)
        self.assertNotIn("history", suggestions.json())
        self.assertEqual(len(self.read(cid).json()["messages"]), 2)
        with self.make_client() as another:
            result = another.get(f"/api/v1/conversations/{cid}/messages", headers=self.ops)
            self.assertEqual(len(result.json()["messages"]), 2)

    def test_search_rename_pagination_fork_export_and_delete(self):
        cid = self.create()
        self.turn(cid, "First stock question")
        self.turn(cid, "Second stock question")
        page = self.read(cid).json()
        renamed = self.client.post(f"/api/v1/conversations/{cid}/rename", headers=self.ops,
            json={"title": "Saved stock discussion", "revision": page["conversation"]["revision"]})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(self.client.post(f"/api/v1/conversations/{cid}/rename", headers=self.ops,
            json={"title": "Stale edit", "revision": page["conversation"]["revision"]}).status_code, 409)
        found = self.client.get("/api/v1/conversations?q=Second", headers=self.ops).json()
        self.assertEqual(found["conversations"][0]["id"], cid)
        latest = self.client.get(f"/api/v1/conversations/{cid}/messages?before=2147483647&limit=2", headers=self.ops).json()
        self.assertEqual([m["sequence"] for m in latest["messages"]], [2, 3])
        branch = self.client.post(f"/api/v1/conversations/{cid}/fork", headers=self.ops,
            json={"message_id": page["messages"][2]["id"]})
        self.assertEqual(branch.status_code, 200)
        self.assertEqual(branch.json()["draft"], "Second stock question")
        exported = self.client.get(f"/api/v1/conversations/{cid}/export", headers=self.ops)
        self.assertEqual(len(exported.json()["messages"]), 4)
        self.assertIn("attachment;", exported.headers["content-disposition"])
        self.assertEqual(self.client.post(f"/api/v1/conversations/{cid}/delete", headers=self.ops).status_code, 200)
        self.assertEqual(self.read(cid).status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/conversations/{cid}/export", headers=self.ops).status_code, 404)

    def test_document_duplicate_scope_source_and_current_translation_proof(self):
        cid = self.create(self.support, {"view": "knowledge", "expert": "support", "module": "financial"})
        context = access.context_for_token(self.support["Authorization"].split()[1])
        source = sorted(experts.access(context, "support", "financial").sources)[0]
        headers = self.headers(cid, auth=self.support)
        body = {"module": "financial", "question": "How do I list vouchers?", "source": source}
        with patch.object(experts, "answer", side_effect=fake_answer) as provider:
            first = self.client.post("/api/v1/experts/support", headers=headers, json=body)
            second = self.client.post("/api/v1/experts/support", headers=headers, json=body)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json(), second.json())
            mismatch = self.client.post("/api/v1/experts/support", headers=headers,
                json=body | {"module": "inventory"})
            self.assertEqual(mismatch.status_code, 409)
            changed = self.client.post("/api/v1/experts/support", headers=headers,
                json=body | {"question": "A different question"})
            self.assertEqual(changed.status_code, 409)
            self.assertEqual(provider.call_count, 1)
        with patch("spia.security.presenter_sessions.time.time", return_value=time.time()+2):
            renewed = self.auth("demo_support")
        page = self.read(cid, renewed).json()
        proof = page["messages"][1]["payload"]["translation_proof"]
        self.assertNotEqual(proof, first.json()["translation_proof"])
        fork = self.client.post(f"/api/v1/conversations/{cid}/fork", headers=renewed,
            json={"message_id": page["messages"][0]["id"]})
        self.assertEqual(fork.json()["source"], source)

    def test_urdu_screenshot_and_screenshot_only_capture(self):
        with Image.new("RGB", (64, 64), "white") as image, BytesIO() as output:
            image.save(output, format="PNG")
            raw = output.getvalue()
        question = "\u06cc\u06c1 \u0645\u0633\u0626\u0644\u06c1 \u06a9\u06cc\u0648\u06ba \u06c1\u06d2\u061f"
        cid = self.create(self.support, {"view": "knowledge", "expert": "support", "module": "financial"})
        headers = self.headers(cid, question, self.support) | {"Content-Type": "image/png"}
        path = "/api/v1/experts/image-question?expert=support_expert&module=financial"
        with patch("spia.integrations.groq.inspect_screenshot", return_value="Visible validation error") as vision, patch.object(experts, "answer", side_effect=fake_answer):
            result = self.client.post(path, headers=headers, content=raw)
            self.assertEqual(result.status_code, 200, result.text)
            repeated = self.client.post(path, headers=headers, content=raw)
            self.assertEqual(repeated.status_code, 200)
            self.assertEqual(vision.call_count, 1)
            headers = self.headers(cid, auth=self.support) | {"Content-Type": "image/png"}
            headers.pop("X-SPIA-Question")
            only = self.client.post(path, headers=headers, content=raw)
            self.assertEqual(only.status_code, 200, only.text)
        page = self.read(cid, self.support).json()
        self.assertEqual(page["messages"][0]["content"], question)
        self.assertTrue(base64.b64decode(page["messages"][0]["image_base64"]).startswith(b"\xff\xd8"))
        self.assertEqual(page["messages"][2]["content"], "Explain this ERP screen or error in English.")
        exported = self.client.get(f"/api/v1/conversations/{cid}/export", headers=self.support).json()
        self.assertNotIn("image_base64", exported["messages"][0])
        self.assertEqual(exported["messages"][0]["attachment"], "Screenshot attached")

    def test_approved_notices_and_arbitrary_answer_rejection(self):
        cid = self.create()
        body = {"question": "Please clarify this request", "notice": sorted(BUSINESS_NOTICES)[0], "request_id": str(uuid.uuid4())}
        result = self.client.post(f"/api/v1/conversations/{cid}/notice", headers=self.ops, json=body)
        self.assertEqual(result.status_code, 200, result.text)
        again = self.client.post(f"/api/v1/conversations/{cid}/notice", headers=self.ops, json=body)
        self.assertEqual(result.json(), again.json())
        bad = self.client.post(f"/api/v1/conversations/{cid}/notice", headers=self.ops,
            json=body | {"notice": "An arbitrary answer with restricted figures"})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(len(self.read(cid).json()["messages"]), 2)

    def test_provider_errors_and_business_denials_are_saved_safely(self):
        cid = self.create(self.support, {"view": "knowledge", "expert": "support", "module": "financial"})
        headers = self.headers(cid, auth=self.support)
        context = access.context_for_token(self.support["Authorization"].split()[1])
        source = sorted(experts.access(context, "support", "financial").sources)[0]
        body = {"module": "financial", "question": "List vouchers", "source": source}
        with patch.object(experts, "answer", side_effect=HTTPException(502, "private-provider-diagnostic")) as provider:
            for _ in range(2):
                result = self.client.post("/api/v1/experts/support", headers=headers, json=body)
                self.assertEqual(result.status_code, 502, result.text)
            self.assertEqual(provider.call_count, 1)
        page = self.read(cid, self.support)
        self.assertNotIn("private-provider-diagnostic", page.text)
        self.assertEqual(page.json()["messages"][1]["payload"]["history_error"], 502)
        self.assertEqual(page.json()["messages"][1]["payload"]["history_source"], source)
        business_id = self.create()
        denied = self.client.get("/api/v1/business/payroll/PAY-2026-09-1002", headers=self.headers(business_id))
        self.assertEqual(denied.status_code, 403)
        saved = self.read(business_id)
        self.assertNotIn("gross_salary", saved.text)
        self.assertEqual(saved.json()["messages"][1]["payload"]["history_error"], 403)

    def test_concurrent_duplicate_and_delete_during_provider_work(self):
        cid = self.create(self.support, {"view": "knowledge", "expert": "support", "module": "financial"})
        entered, release = threading.Event(), threading.Event()
        def slow(*args, **kwargs):
            answer = fake_answer(*args, **kwargs)
            entered.set()
            release.wait(10)
            return answer
        headers = self.headers(cid, auth=self.support)
        def request():
            return self.client.post("/api/v1/experts/support", headers=headers,
                json={"module": "financial", "question": "List vouchers"})
        with patch.object(experts, "answer", side_effect=slow) as provider, ThreadPoolExecutor(2) as pool:
            pending = pool.submit(request)
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(request().status_code, 409)
                result = self.client.post(f"/api/v1/conversations/{cid}/delete", headers=self.support)
                self.assertEqual(result.status_code, 200, result.text)
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=10).status_code, 404)
            self.assertEqual(provider.call_count, 1)
        with history.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chat_message").fetchone()[0], 0)

    def test_access_change_blocks_read_export_and_late_response(self):
        cid = self.create(self.support, {"view": "knowledge", "expert": "support", "module": "financial"})
        with patch.object(experts, "answer", side_effect=fake_answer):
            self.client.post("/api/v1/experts/support", headers=self.headers(cid, auth=self.support),
                json={"module": "financial", "question": "First question"})
        entered, release = threading.Event(), threading.Event()
        def slow(*args, **kwargs):
            answer = fake_answer(*args, **kwargs)
            entered.set()
            release.wait(10)
            return answer
        with patch.object(experts, "answer", side_effect=slow), ThreadPoolExecutor(1) as pool:
            pending = pool.submit(lambda: self.client.post("/api/v1/experts/support",
                headers=self.headers(cid, auth=self.support), json={"module": "financial", "question": "Second question"}))
            try:
                self.assertTrue(entered.wait(5))
                path = self.root / "catalogue.json"
                catalogue = json.loads(path.read_text())
                for item in catalogue["sources"]:
                    if item["expert"] == "support":
                        item["status"] = "blocked"
                path.write_text(json.dumps(catalogue))
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=10).status_code, 403)
        self.assertEqual(self.read(cid, self.support).status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/conversations/{cid}/export", headers=self.support).status_code, 403)
        listed = self.client.get("/api/v1/conversations", headers=self.support).json()["conversations"][0]
        self.assertEqual(listed["title"], "Unavailable conversation")
        self.assertIsNone(listed["scope"])
        with history.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chat_message").fetchone()[0], 2)

    def test_cors_and_hosted_session_only_mode(self):
        result = self.client.options("/api/v1/experts/support", headers={"Origin": "https://example.test",
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,x-spia-conversation,x-spia-request-id"})
        self.assertEqual(result.status_code, 200, result.text)
        result = self.client.get("/api/v1/conversations", headers={"Origin": "https://example.test"})
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.headers["access-control-allow-origin"], "https://example.test")
        cid = self.create()
        headers = self.headers(cid) | {"Origin": "https://example.test"}
        for _ in range(2):
            result = self.client.get(self.order_path, headers=headers)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.headers["access-control-allow-origin"], "https://example.test")
        with patch.dict(os.environ, {"VERCEL": "1"}):
            status = self.client.get("/api/v1/conversations/status", headers=self.ops)
            self.assertFalse(status.json()["enabled"])

    def test_bad_headers_and_oversized_input_stop_before_provider(self):
        cid = self.create(self.support, {"view": "knowledge", "expert": "support", "module": "financial"})
        headers = self.headers(cid, auth=self.support)
        with patch.object(experts, "answer", side_effect=fake_answer) as provider:
            bad = self.client.post("/api/v1/experts/support", headers=headers | {"X-SPIA-Request-ID": "bad-id"},
                json={"module": "financial", "question": "List vouchers"})
            self.assertEqual(bad.status_code, 422)
            large = self.client.post("/api/v1/experts/support", headers=headers | {"Content-Type": "application/json"}, content=b"x"*8193)
            self.assertEqual(large.status_code, 413)
            self.assertEqual(provider.call_count, 0)
        huge = self.client.post("/api/v1/conversations", headers=self.ops | {"Content-Type": "application/json"}, content=b"x"*16385)
        self.assertEqual(huge.status_code, 413)
        duplicates = list(headers.items()) + [("X-SPIA-Question", "another")]
        result = self.client.post("/api/v1/experts/support", headers=duplicates,
            json={"module": "financial", "question": "List vouchers"})
        self.assertEqual(result.status_code, 422)
        self.assertFalse(self.read(cid, self.support).json()["messages"])


if __name__ == "__main__":
    unittest.main()
