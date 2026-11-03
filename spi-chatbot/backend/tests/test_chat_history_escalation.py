"""Isolated escalation tests. No AI requests or WhatsApp messages are sent."""
import json
import os
import unittest
import uuid
from dataclasses import replace
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
import test_chat_history_storage as base
from spia.services import chat_history as h
from spia.services import escalation as e
from spia.api import escalations as api
from spia.api.access import require_access_context

class EscalationTests(unittest.TestCase):
    def setUp(self):
        base.HistoryStorageTests.setUp(self)
        isolated=patch.dict(os.environ,{
            'SPIA_ESCALATION_CONTACTS_FILE':str(self.root/'whatsapp_contacts.json')
        })
        isolated.start()
        self.addCleanup(isolated.stop)

    login=base.HistoryStorageTests.login
    create=base.HistoryStorageTests.create
    denied=base.HistoryStorageTests.denied

    def contacts(self,context):
        config={
            'company_id':context.identity.company_id,
            'installation_id':context.identity.installation_id,
            'contacts':[
                {'id':'support-1','department':'support','name':'Support 1','phone':'923000000001'},
                {'id':'implementation-1','department':'implementation','name':'Implementation 1','phone':'923000000002'},
            ],
        }
        path=e.contacts_path()
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(config),encoding='utf-8')
        return path

    def saved(self,question='The report is not working',missing=True,image=None):
        context=self.login('demo_support')
        cid=self.create({
            'view':'knowledge','expert':'support','module':'financial'
        },context)
        reply,metadata=e.pack_reply(
            e.MARKER+'No documented answer.' if missing
            else 'Select Voucher type and try again.',
            'support'
        )
        rid=str(uuid.uuid4())
        h.claim(context,cid,rid,'fixture-'+rid)
        result=h.finish(context,cid,rid,question,{
            'reply':reply,'escalation':metadata,'language':'en','sources':[]
        },image=image)
        return context,cid,result['history']['answer_message_id']

    def test_signals_do_not_treat_empty_sources_as_missing(self):
        self.assertFalse(e.pack_reply('Select Voucher type and try again.','support')[1]['eligible'])
        self.assertFalse(e.pack_reply('Which accounting period do you mean?','support')[1]['eligible'])
        self.assertTrue(e.pack_reply(e.LEGACY_EN,'support')[1]['eligible'])
        self.assertTrue(e.pack_reply(e.LEGACY_UR,'support')[1]['eligible'])
        reply,flag=e.pack_reply(e.MARKER+'Missing detail.','implementation')
        self.assertEqual(reply,'Missing detail.')
        self.assertTrue(flag['eligible'])

    def test_automatic_routing_and_ambiguous_fallback(self):
        self.assertEqual(e.department('Installation failed','support')[0],'implementation')
        self.assertEqual(e.department('Report nahi chal rahi','implementation')[0],'support')
        self.assertEqual(e.department('Configure opening balances','support')[0],'implementation')
        self.assertEqual(e.department('What should I do?','support')[0],'support')
        self.assertIsNone(e.department('What should I do?','project_knowledge')[0])
        self.assertEqual(e.department('رپورٹ نہیں چل رہی','implementation')[0],'support')

    def test_international_contacts_validation(self):
        c=e.Contact(id='one',department='support',name='Support',phone='+92 300 0000001')
        self.assertEqual(c.phone,'923000000001')
        for value in ('03000000001','https://example.test','923000000001?x=bad'):
            with self.assertRaises(ValueError):
                e.Contact(id='one',department='support',name='Support',phone=value)

    def test_prepare_uses_server_question_and_contact(self):
        context,cid,mid=self.saved()
        self.contacts(context)
        result=api.prepare(context,cid,mid)
        self.assertEqual(result['recommended'],'support')
        self.assertEqual(len(result['contacts']),2)
        parts=urlsplit(result['contacts'][0]['url'])
        self.assertEqual(parts.netloc,'wa.me')
        self.assertEqual(parts.path,'/923000000001')
        text=parse_qs(parts.query)['text'][0]
        self.assertIn('The report is not working',text)
        self.assertNotIn(e.MARKER,text)

    def test_history_replay_preserves_missing_knowledge(self):
        context,cid,mid=self.saved()
        payload=h.messages(context,cid)['messages'][-1]['payload']
        self.assertTrue(payload['escalation']['eligible'])
        self.assertNotIn(e.MARKER,payload['reply'])

    def test_cross_user_company_and_access_denial(self):
        context,cid,mid=self.saved()
        self.denied(404,lambda:api.prepare(self.other,cid,mid))
        foreign=replace(context,identity=context.identity.model_copy(update={'company_id':'OTHER'}))
        self.denied(404,lambda:api.prepare(foreign,cid,mid))
        with patch.object(h,'authorize',side_effect=HTTPException(403,'Denied')):
            self.denied(403,lambda:api.prepare(context,cid,mid))

    def test_supported_screenshot_answer_cannot_escalate(self):
        context,cid,mid=self.saved(missing=False)
        self.denied(409,lambda:api.prepare(context,cid,mid))

    def test_screenshot_notice_and_urdu_url_encoding(self):
        context,cid,mid=self.saved(image=b'fictional-sanitized-image')
        self.contacts(context)
        result=api.prepare(context,cid,mid)
        self.assertTrue(result['has_image'])
        self.assertIn('separately',result['messages']['support'])
        text=e.message('سوال','financial','support','reference',True)
        decoded=parse_qs(urlsplit(e.whatsapp_url('923000000001',text)).query)['text'][0]
        self.assertEqual(decoded,text)

    def test_contacts_missing_wrong_company_and_reload(self):
        context,cid,mid=self.saved()
        self.assertFalse(api.prepare(context,cid,mid)['contacts'])
        path=self.contacts(context)
        self.assertEqual(len(api.prepare(context,cid,mid)['contacts']),2)
        config=json.loads(path.read_text())
        config['contacts']=config['contacts'][:1]
        path.write_text(json.dumps(config))
        self.assertEqual(len(api.prepare(context,cid,mid)['contacts']),1)
        config['company_id']='OTHER'
        path.write_text(json.dumps(config))
        self.denied(503,lambda:api.prepare(context,cid,mid))

    def test_http_authentication_and_client_data_rejected(self):
        app=FastAPI()
        app.include_router(api.router)
        context,cid,mid=self.saved()
        with TestClient(app) as client:
            body={'conversation_id':cid,'message_id':mid}
            self.assertEqual(client.post('/api/v1/escalations/prepare',json=body).status_code,401)
            app.dependency_overrides[require_access_context]=lambda:context
            self.assertEqual(client.post('/api/v1/escalations/prepare',json={**body,'phone':'123'}).status_code,422)
            result=client.post('/api/v1/escalations/prepare',json=body)
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.headers['cache-control'],'no-store')
