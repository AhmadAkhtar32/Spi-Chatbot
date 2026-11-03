"""Live WhatsApp checks; no AI or WhatsApp requests are sent."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from spia.api import escalations as api
from spia.api import experts as x
from spia.api.access import require_access_context
from spia.services import escalation as e
from spia.services import chat_history as h

class LiveWhatsAppTests(unittest.TestCase):
    def setUp(self):
        changes=patch.dict(os.environ,{
            'VERCEL':'1',
            'SPIA_WHATSAPP_SUPPORT':'923000000001',
            'SPIA_WHATSAPP_IMPLEMENTATION':'923000000002',
            'SPIA_RESPONSE_SIGNING_SECRET':'fictional-live-test-secret-'*3,
        })
        changes.start()
        self.addCleanup(changes.stop)
        self.context=SimpleNamespace(identity=SimpleNamespace(
            company_id='TEST',installation_id='TEST-INSTALL',user_id='TEST-USER'
        ))
        self.view=SimpleNamespace(sources={'guide.txt'})
        for name,value in (
            ('access',self.view),('reply_proof','a'*64),('confirm',None)
        ):
            mocked=patch.object(x,name,return_value=value)
            setattr(self,name,mocked.start())
            self.addCleanup(mocked.stop)
        database=patch.object(
            h,'connection',
            side_effect=AssertionError('Live handover must not use SQLite')
        )
        database.start()
        self.addCleanup(database.stop)
        self.body=api.LivePrepare(
            expert='support',module='financial',
            reply='Missing documented answer.',language='en',
            sources=['guide.txt'],
            question='My report has an unknown error.',
            proof=e.live_escalation_proof('a'*64),
        )

    def test_serverless_no_database(self):
        result=api.prepare_live(self.context,self.body)
        self.assertEqual(result['recommended'],'support')
        self.assertEqual(len(result['contacts']),2)
        self.assertTrue(result['contacts'][0]['url'].startswith(
            'https://wa.me/923000000001?text='
        ))
        self.access.assert_called_once_with(self.context,'support','financial')
        self.confirm.assert_called_once_with(self.view)

    def test_forged_or_expired_proof_rejected(self):
        for proof in ('0'*64,e.live_escalation_proof('b'*64)):
            with self.assertRaises(HTTPException) as caught:
                api.prepare_live(
                    self.context,self.body.model_copy(update={'proof':proof})
                )
            self.assertEqual(caught.exception.status_code,403)

    def test_source_and_current_access_checked(self):
        self.view.sources=set()
        with self.assertRaises(HTTPException) as caught:
            api.prepare_live(self.context,self.body)
        self.assertEqual(caught.exception.status_code,403)
        self.access.side_effect=HTTPException(403,'Access changed')
        with self.assertRaises(HTTPException) as caught:
            api.prepare_live(self.context,self.body)
        self.assertEqual(caught.exception.status_code,403)

    def test_invalid_environment_number_rejected(self):
        with patch.dict(os.environ,{'SPIA_WHATSAPP_SUPPORT':'03000000001'}):
            with self.assertRaises(HTTPException) as caught:
                api.prepare_live(self.context,self.body)
            self.assertEqual(caught.exception.status_code,503)

    def test_http_authentication_extra_fields_and_no_store(self):
        app=FastAPI()
        app.include_router(api.router)
        with TestClient(app) as client:
            body=self.body.model_dump()
            url='/api/v1/escalations/prepare-live'
            self.assertEqual(client.post(url,json=body).status_code,401)
            app.dependency_overrides[require_access_context]=lambda:self.context
            self.assertEqual(
                client.post(url,json={**body,'user_id':'other'}).status_code,422
            )
            response=client.post(url,json=body)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['cache-control'],'no-store')
