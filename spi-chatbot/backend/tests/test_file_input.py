
"""Offline document parsing, protected attachment storage and API checks."""
import io
import json
import os
import unittest
import uuid
import zipfile
from functools import lru_cache
from unittest.mock import patch
from fastapi import HTTPException
from reportlab.pdfgen import canvas
from spia.api import experts
from spia.services import chat_files as files, chat_history as history
import test_chat_history_api as api_checks

@lru_cache(maxsize=16)
def word(text="Read the Voucher type field before running the report."):
    output = io.BytesIO()
    from xml.sax.saxutils import escape
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<Types><Override ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+escape(text)+'</w:t></w:r></w:p></w:body></w:document>')
    return output.getvalue()

def pdf():
    output = io.BytesIO()
    c = canvas.Canvas(output)
    c.drawString(50, 750, "Select Voucher type before running the report.")
    c.save()
    return output.getvalue()

class FileParserTests(unittest.TestCase):
    def test_pdf_and_urdu_word(self):
        self.assertIn("Voucher type", files.text(files.upload(pdf(), files.PDF, "guide.pdf")))
        text = "\u0648\u0627\u0686\u0631 \u0679\u0627\u0626\u067e \u0645\u0646\u062a\u062e\u0628 \u06a9\u0631\u06cc\u06ba"
        self.assertIn(text, files.text(files.upload(word(text), files.DOCX, "guide.docx")))

    def test_bad_file_types_names_and_sizes(self):
        for raw, mime, name in [(b"x", files.PDF, "a.pdf"), (pdf(),files.PDF,"../a.pdf"),
                (pdf(),files.DOCX,"a.pdf"), (word(),"application/msword","a.doc"),
                (b"x"*(files.MAX_BYTES+1),files.PDF,"a.pdf")]:
            with self.assertRaises(HTTPException):
                files.upload(raw,mime,name)

    def test_blank_and_encrypted_pdf(self):
        from pypdf import PdfWriter
        for encrypted in (False,True):
            w=PdfWriter()
            w.add_blank_page(100,100)
            if encrypted:
                w.encrypt("test")
            output=io.BytesIO()
            w.write(output)
            with self.assertRaises(HTTPException):
                files.text(files.upload(output.getvalue(),files.PDF,"scan.pdf"))

    def test_zip_bomb_and_xml_entities(self):
        for body in ("x"*500000, '<!DOCTYPE x [<!ENTITY x "example">]><x>&x;</x>'):
            output=io.BytesIO()
            with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as z:
                z.writestr("[Content_Types].xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
                z.writestr("word/document.xml",body)
            with self.assertRaises(HTTPException):
                files.text(files.upload(output.getvalue(),files.DOCX,"bad.docx"))

    def test_timeout_releases_reader(self):
        import subprocess
        with patch.object(files.subprocess,"run",side_effect=subprocess.TimeoutExpired("reader",18)):
            with self.assertRaises(HTTPException):
                files.text(files.upload(pdf(),files.PDF,"a.pdf"))
        self.assertIn("Voucher",files.text(files.upload(pdf(),files.PDF,"a.pdf")))

class DocumentAPITests(unittest.TestCase):
    setUp = api_checks.HistoryAPITests.setUp
    login = api_checks.HistoryAPITests.login
    make_client = api_checks.HistoryAPITests.make_client
    auth = api_checks.HistoryAPITests.auth
    create = api_checks.HistoryAPITests.create
    headers = api_checks.HistoryAPITests.headers
    read = api_checks.HistoryAPITests.read

    def send_file(self, cid, raw=None, filename="guide.docx", **kwargs):
        from urllib.parse import urlencode
        path="/api/v1/experts/document-question?"+urlencode({"expert":"support_expert","module":"financial","filename":filename})
        headers=self.headers(cid,kwargs.pop("question","Summarize this document"),self.support,**kwargs)|{"Content-Type":files.DOCX}
        return self.client.post(path,headers=headers,content=raw or word())

    def start(self):
        return self.create(self.support,{"view":"knowledge","expert":"support","module":"financial"})

    def test_roundtrip_idempotence_fork_and_delete(self):
        cid=self.start()
        rid=str(uuid.uuid4())
        with patch.object(experts,"answer",side_effect=api_checks.fake_answer) as model:
            first=self.send_file(cid,rid=rid)
            self.assertEqual(first.status_code,200,first.text)
            repeated=self.send_file(cid,rid=rid)
            self.assertEqual(first.json(),repeated.json())
            self.assertEqual(model.call_count,1)
            self.assertIn("Voucher type",model.call_args.kwargs["attachment_text"])
            self.assertFalse(model.call_args.kwargs["use_cache"])
            self.assertEqual(self.send_file(cid).status_code,200)
        page=self.read(cid,self.support).json()
        a=page["messages"][0]["attachment"]
        self.assertNotIn("image_base64",page["messages"][0])
        url=f"/api/v1/conversations/{cid}/attachments/{a['message_id']}"
        good=self.client.get(url,headers=self.support)
        self.assertEqual(good.content,word())
        self.assertEqual(good.headers["x-content-type-options"],"nosniff")
        self.assertEqual(self.client.get(url,headers=self.employee).status_code,404)
        self.assertEqual(self.client.get(url).status_code,401)
        fork=self.client.post(f"/api/v1/conversations/{cid}/fork",headers=self.support,json={"message_id":page["messages"][2]["id"]})
        self.assertEqual(fork.status_code,200,fork.text)
        self.assertEqual(fork.json()["attachment"]["filename"],"guide.docx")
        branch=fork.json()["conversation"]["id"]
        copied=self.read(branch,self.support).json()["messages"][0]["attachment"]
        copied_url=f"/api/v1/conversations/{branch}/attachments/{copied['message_id']}"
        self.assertEqual(self.client.get(copied_url,headers=self.support).content,word())
        self.client.post(f"/api/v1/conversations/{cid}/delete",headers=self.support)
        self.assertEqual(self.client.get(url,headers=self.support).status_code,404)
        self.assertEqual(self.client.get(copied_url,headers=self.support).status_code,200)

    def test_denied_before_extraction_and_bad_document(self):
        cid=self.start()
        with patch.object(files,"text") as reader,patch.object(experts,"answer") as model:
            path="/api/v1/experts/document-question?expert=support_expert&module=financial&filename=guide.docx"
            self.assertEqual(self.client.post(path,content=word(),headers={"Content-Type":files.DOCX}).status_code,401)
            self.assertEqual(self.client.post(path,content=word(),headers=self.employee|{"Content-Type":files.DOCX}).status_code,403)
            self.assertEqual(reader.call_count,0)
            self.assertEqual(model.call_count,0)
        result=self.send_file(cid,raw=b"PK\x03\x04broken")
        self.assertEqual(result.status_code,422,result.text)
        with history.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chat_attachment").fetchone()[0],0)

    def test_authority_change_blocks_download(self):
        cid=self.start()
        with patch.object(experts,"answer",side_effect=api_checks.fake_answer):
            self.assertEqual(self.send_file(cid).status_code,200)
        message=self.read(cid,self.support).json()["messages"][0]["id"]
        catalogue=self.root/"catalogue.json"
        data=json.loads(catalogue.read_text())
        for source in data["sources"]:
            if source["expert"]=="support":
                source["status"]="blocked"
        catalogue.write_text(json.dumps(data))
        url=f"/api/v1/conversations/{cid}/attachments/{message}"
        self.assertEqual(self.client.get(url,headers=self.support).status_code,403)

    def test_attachment_only_default_matches_saved_question(self):
        cid=self.start()
        headers=self.headers(cid,auth=self.support)|{"Content-Type":files.DOCX}
        headers.pop("X-SPIA-Question")
        path="/api/v1/experts/document-question?expert=support_expert&module=financial&filename=guide.docx"
        with patch.object(experts,"answer",side_effect=api_checks.fake_answer) as model:
            result=self.client.post(path,headers=headers,content=word())
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(model.call_args.args[1].question,"Summarize this document in English.")
        self.assertEqual(self.read(cid,self.support).json()["messages"][0]["content"],"Summarize this document in English.")

    def test_package_and_module_denial_before_reader(self):
        import base64
        from datetime import datetime,timedelta,timezone
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from spia.security.license_policy import SIGNING_CONTEXT
        path=self.root/"security/company_license.json"
        original=path.read_bytes()
        key=load_pem_private_key((self.root/"issuer.pem").read_bytes(),password=b"fictional-history-test-password")
        url="/api/v1/experts/document-question?expert=support_expert&module=financial&filename=guide.docx"
        for group,name in (("packages","support_expert"),("modules","financial")):
            envelope=json.loads(original)
            value=json.loads(base64.urlsafe_b64decode(envelope["payload"]))
            for item in value[group]:
                if item.get("feature",item.get("module"))==name:
                    item["starts_at"]=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
                    item["expires_at"]=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
            raw=json.dumps(value,separators=(",",":")).encode()
            envelope["payload"]=base64.urlsafe_b64encode(raw).decode()
            envelope["signature"]=base64.urlsafe_b64encode(key.sign(SIGNING_CONTEXT+envelope["key_id"].encode()+b"\0"+raw)).decode()
            path.write_text(json.dumps(envelope))
            with patch.object(files,"text") as reader:
                response=self.client.post(url,headers=self.support|{"Content-Type":files.DOCX},content=word())
                self.assertEqual(response.status_code,403,response.text)
                reader.assert_not_called()
            path.write_bytes(original)

    def test_private_text_uses_existing_answer_without_shared_cache(self):
        import sys
        from types import SimpleNamespace as NS
        from unittest.mock import MagicMock
        from fastapi import Response
        context=self.login("demo_support")
        view=experts.access(context,"support","financial")
        vector=view.chunks[0]["embedding"]
        completion=NS(choices=[NS(message=NS(content="The attached document describes voucher selection."),finish_reason="stop")])
        with patch.dict(os.environ,{"GROQ_API_KEY":"offline-test-key"}),patch.dict(sys.modules,{"groq":NS(Groq=MagicMock())}),patch.object(experts,"embed_texts",return_value=[vector]),patch.object(experts,"generate_with_retry",return_value=completion) as model,patch.object(experts.document_answers,"get") as cached,patch.object(experts.document_answers,"put") as save:
            result=experts.answer("support",experts.ExpertQuestion(module="financial",question="Summarize the attachment"),context,Response(),attachment_text="Unique private attachment text.")
            self.assertIn("attached document",result["reply"])
            self.assertIn("Unique private attachment text.",model.call_args.kwargs["messages"][1]["content"])
            cached.assert_not_called()
            save.assert_not_called()

    def test_quota_rolls_back_and_serverless_is_temporary(self):
        cid=self.start()
        with patch.dict(os.environ,{"SPIA_MAX_DOCUMENT_STORAGE_MIB":"1"}),patch.object(experts,"answer",side_effect=api_checks.fake_answer):
            self.assertEqual(self.send_file(cid).status_code,200)
            with history.connection(write=True) as db:
                db.execute("UPDATE chat_attachment SET content=?",(b"x"*(1024*1024),))
            self.assertEqual(self.send_file(cid).status_code,409)
            self.assertEqual(len(self.read(cid,self.support).json()["messages"]),2)
        path="/api/v1/experts/document-question?expert=support_expert&module=financial&filename=guide.docx"
        with patch.dict(os.environ,{"VERCEL":"1"}),patch.object(experts,"answer",side_effect=api_checks.fake_answer):
            result=self.client.post(path,headers=self.support|{"Content-Type":files.DOCX},content=word())
            self.assertEqual(result.status_code,200,result.text)
            self.assertNotIn("history",result.json())

if __name__=="__main__":
    unittest.main()
