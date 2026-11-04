"""Feedback checks using isolated fictional history/security fixtures."""
import unittest
from dataclasses import replace
from unittest.mock import patch
from fastapi import FastAPI,HTTPException,Response
from fastapi.testclient import TestClient
import test_chat_history_storage as base
from spia.api import feedback as f
from spia.api.access import require_access_context
from spia.services import chat_history as h

class FeedbackTests(unittest.TestCase):
    setUp=base.HistoryStorageTests.setUp
    login=base.HistoryStorageTests.login
    create=base.HistoryStorageTests.create
    turn=base.HistoryStorageTests.turn
    denied=base.HistoryStorageTests.denied

    def pair(self):
        cid=self.create()
        ids=self.turn(cid)['history']
        return cid,ids['user_message_id'],ids['answer_message_id']

    def test_vote_change_clear_and_idempotence(self):
        cid,qid,mid=self.pair()
        first=f.save(self.user,cid,mid,'up')
        self.assertEqual(first,f.save(self.user,cid,mid,'up'))
        changed=f.save(self.user,cid,mid,'down')
        self.assertEqual(changed['created_at'],first['created_at'])
        self.assertEqual(changed['rating'],'down')
        self.assertEqual(len(f.ratings(self.user,cid)['items']),1)
        self.assertIsNone(f.save(self.user,cid,mid,None)['rating'])
        self.assertFalse(f.ratings(self.user,cid)['items'])
        self.assertEqual(len(h.messages(self.user,cid)['messages']),2)

    def test_new_session_and_question_link(self):
        cid,qid,mid=self.pair()
        f.save(self.user,cid,mid,'up')
        vote=f.ratings(self.login('demo_operations'),cid)['items'][0]
        self.assertEqual(vote['question_id'],qid)
        self.assertEqual(vote['message_id'],mid)
        with h.connection() as db:
            row=db.execute('SELECT * FROM chat_feedback').fetchone()
            self.assertEqual(
                (row['company_id'],row['installation_id'],row['user_id']),
                h.owner(self.user)
            )

    def test_other_user_company_and_conversation_rejected(self):
        cid,qid,mid=self.pair()
        self.denied(404,lambda:f.save(self.other,cid,mid,'up'))
        foreign=replace(
            self.user,
            identity=self.user.identity.model_copy(update={'company_id':'OTHER'})
        )
        self.denied(404,lambda:f.ratings(foreign,cid))
        other=self.create()
        self.denied(404,lambda:f.save(self.user,other,mid,'up'))
        self.denied(404,lambda:f.save(self.user,cid,qid,'up'))

    def test_deleted_or_revoked_chat_rejected(self):
        cid,qid,mid=self.pair()
        with patch.object(h,'authorize',side_effect=HTTPException(403,'Denied')):
            self.denied(403,lambda:f.save(self.user,cid,mid,'up'))
        h.delete(self.user,cid)
        self.denied(404,lambda:f.save(self.user,cid,mid,'up'))

    def test_serverless_status_does_not_use_database(self):
        with patch.dict('os.environ',{'VERCEL':'1'}),patch.object(
            h,'connection',side_effect=AssertionError('No database in preview')
        ):
            self.assertFalse(f.status(Response(),self.user)['enabled'])
            self.denied(503,lambda:f.save(self.user,'unused','unused','up'))

    def test_http_auth_validation_and_no_store(self):
        app=FastAPI()
        app.include_router(f.router)
        cid,qid,mid=self.pair()
        url=f'/api/v1/feedback/{cid}/{mid}'
        with TestClient(app) as client:
            self.assertEqual(client.post(url,json={'rating':'up'}).status_code,401)
            app.dependency_overrides[require_access_context]=lambda:self.user
            self.assertEqual(
                client.post(url,json={'rating':'up','user_id':'other'}).status_code,422
            )
            self.assertEqual(client.post(url,json={'rating':'bad'}).status_code,422)
            response=client.post(url,json={'rating':'down'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['cache-control'],'no-store')
