"""Pin tests use isolated fictional security/data from the existing history tests."""
import sqlite3
import unittest
from dataclasses import replace
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import test_chat_history_storage as base
from spia.services import chat_history as h
from spia.api import history_pins as p
from spia.api.access import require_access_context

class HistoryPinTests(unittest.TestCase):
    setUp=base.HistoryStorageTests.setUp
    login=base.HistoryStorageTests.login
    create=base.HistoryStorageTests.create
    turn=base.HistoryStorageTests.turn
    denied=base.HistoryStorageTests.denied

    def revision(self,cid):
        return h.messages(self.user,cid)['conversation']['revision']

    def test_pin_persists_for_same_user_new_session(self):
        cid=self.create()
        self.turn(cid)
        before=self.revision(cid)
        saved=p.set_pin(self.user,cid,True,before)
        self.assertEqual(saved['revision'],before+1)
        pins=p.list_pins(self.login('demo_operations'))['conversations']
        self.assertEqual([c['id'] for c in pins],[cid])
        self.assertTrue(pins[0]['pinned'])
        self.assertEqual(len(h.messages(self.user,cid)['messages']),2)

    def test_cross_user_company_and_installation(self):
        cid=self.create()
        self.turn(cid)
        p.set_pin(self.user,cid,True,self.revision(cid))
        self.assertFalse(p.list_pins(self.other)['conversations'])
        self.denied(404,lambda:p.set_pin(self.other,cid,False,0))
        for field in ('company_id','installation_id'):
            foreign=replace(
                self.user,
                identity=self.user.identity.model_copy(update={field:'OTHER'})
            )
            self.assertFalse(p.list_pins(foreign)['conversations'])
            self.denied(404,lambda:p.set_pin(foreign,cid,True,0))

    def test_unpin_is_idempotent_and_stale_write_rejected(self):
        cid=self.create()
        old=self.revision(cid)
        saved=p.set_pin(self.user,cid,True,old)
        self.denied(409,lambda:p.set_pin(self.user,cid,False,old))
        again=p.set_pin(self.user,cid,True,saved['revision'])
        self.assertEqual(again,saved)
        cleared=p.set_pin(self.user,cid,False,saved['revision'])
        self.assertFalse(p.list_pins(self.user)['conversations'])
        self.assertFalse(cleared['pinned'])
        self.assertEqual(
            p.set_pin(self.user,cid,False,cleared['revision']),cleared
        )

    def test_deleted_chat_does_not_appear_in_pins(self):
        cid=self.create()
        p.set_pin(self.user,cid,True,self.revision(cid))
        h.delete(self.user,cid)
        self.assertFalse(p.list_pins(self.user)['conversations'])
        self.denied(404,lambda:p.set_pin(self.user,cid,True,0))

    def test_changed_authority_hides_pin_and_blocks_new_pin(self):
        cid=self.create()
        p.set_pin(self.user,cid,True,self.revision(cid))
        with patch.object(h,'authorize',side_effect=HTTPException(403,'Denied')):
            self.assertFalse(p.list_pins(self.user)['conversations'])
            self.denied(403,lambda:p.set_pin(self.user,cid,True,0))

    def test_route_authentication_validation_and_no_store(self):
        app=FastAPI()
        app.include_router(p.router)
        cid=self.create()
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/v1/conversations/pins').status_code,401)
            app.dependency_overrides[require_access_context]=lambda:self.user
            url=f'/api/v1/conversations/{cid}/pin'
            self.assertEqual(
                client.post(url,json={'pinned':'yes','revision':0}).status_code,422
            )
            self.assertEqual(
                client.post(url,json={
                    'pinned':True,'revision':0,'user_id':'other'
                }).status_code,422
            )
            response=client.post(url,json={
                'pinned':True,'revision':self.revision(cid)
            })
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['cache-control'],'no-store')
            result=client.get('/api/v1/conversations/pins')
            self.assertEqual(result.json()['conversations'][0]['id'],cid)
            self.assertEqual(result.headers['cache-control'],'no-store')

    def test_backup_contains_pins(self):
        cid=self.create()
        p.set_pin(self.user,cid,True,self.revision(cid))
        target=h.backup(self.root/'pins-backup.db')
        db=sqlite3.connect(target)
        try:
            self.assertEqual(
                db.execute('SELECT conversation_id FROM chat_pin').fetchone()[0],cid
            )
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        finally:
            db.close()
