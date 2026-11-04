"""Per-answer feedback protected by existing history ownership and access checks."""
import time
from typing import Literal
from fastapi import APIRouter,Depends,Response
from pydantic import BaseModel,ConfigDict
from spia.api.access import require_access_context
from spia.security.access_control import AccessDenied
from spia.services import chat_history as h

router=APIRouter(prefix='/api/v1/feedback',tags=['Answer feedback'])

class Vote(BaseModel):
    model_config=ConfigDict(extra='forbid')
    rating:Literal['up','down']|None

def require_storage():
    if not h.enabled():
        h.fail(503,'Persistent feedback requires the company-hosted backend.')

def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS chat_feedback (
        message_id TEXT PRIMARY KEY REFERENCES chat_message(id) ON DELETE CASCADE,
        conversation_id TEXT NOT NULL REFERENCES chat_master(id) ON DELETE CASCADE,
        question_id TEXT NOT NULL REFERENCES chat_message(id) ON DELETE CASCADE,
        company_id TEXT NOT NULL,
        installation_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        rating TEXT NOT NULL CHECK(rating IN ('up','down')),
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )""")
    db.execute(
        'CREATE INDEX IF NOT EXISTS chat_feedback_conversation '
        'ON chat_feedback(conversation_id)'
    )

def checked(db,context,cid):
    row=h.row_for(db,context,cid)
    h.authorize(context,row)
    return row

def ratings(context,cid):
    require_storage()
    try:
        with h.connection(write=True) as db:
            chat=checked(db,context,cid)
            schema(db)
            rows=db.execute(
                'SELECT message_id,question_id,rating,created_at,updated_at '
                'FROM chat_feedback WHERE conversation_id=?',
                (cid,)
            ).fetchall()
            h.authorize(context,chat)
            return {'items':[dict(row) for row in rows]}
    except AccessDenied:
        h.fail(403,'Current access does not allow this conversation.')

def save(context,cid,mid,rating):
    require_storage()
    h.identifier(mid)
    if rating not in ('up','down',None):
        h.fail(422,'Use up, down or null.')
    try:
        with h.connection(write=True) as db:
            chat=checked(db,context,cid)
            schema(db)
            answer=db.execute(
                "SELECT sequence FROM chat_message WHERE id=? "
                "AND conversation_id=? AND role='assistant'",
                (mid,cid)
            ).fetchone()
            if answer is None:
                h.fail(404,'Answer not found')
            question=db.execute(
                "SELECT id FROM chat_message WHERE conversation_id=? "
                "AND sequence=? AND role='user'",
                (cid,answer['sequence']-1)
            ).fetchone()
            if question is None:
                h.fail(404,'Question not found')
            previous=db.execute(
                'SELECT * FROM chat_feedback WHERE message_id=?',
                (mid,)
            ).fetchone()
            now=int(time.time()*1000)
            if rating is None:
                db.execute('DELETE FROM chat_feedback WHERE message_id=?',(mid,))
            elif previous is None:
                db.execute(
                    'INSERT INTO chat_feedback VALUES(?,?,?,?,?,?,?,?,?)',
                    (mid,cid,question['id'],*h.owner(context),rating,now,now)
                )
            elif previous['rating']!=rating:
                db.execute(
                    'UPDATE chat_feedback SET rating=?,updated_at=? WHERE message_id=?',
                    (rating,now,mid)
                )
            h.authorize(context,chat)
            row=db.execute(
                'SELECT message_id,question_id,rating,created_at,updated_at '
                'FROM chat_feedback WHERE message_id=?',
                (mid,)
            ).fetchone()
            return dict(row) if row else {'message_id':mid,'rating':None}
    except AccessDenied:
        h.fail(403,'Current access does not allow this conversation.')

@router.get('/status')
def status(response:Response,context=Depends(require_access_context)):
    response.headers['Cache-Control']='no-store'
    return {
        'enabled':h.enabled(),
        'notice':'' if h.enabled() else 'This preview cannot save permanent feedback.',
    }

@router.get('/{cid}')
def get_feedback(cid:str,response:Response,context=Depends(require_access_context)):
    response.headers['Cache-Control']='no-store'
    return ratings(context,cid)

@router.post('/{cid}/{mid}')
def vote(cid:str,mid:str,body:Vote,response:Response,context=Depends(require_access_context)):
    response.headers['Cache-Control']='no-store'
    return save(context,cid,mid,body.rating)
