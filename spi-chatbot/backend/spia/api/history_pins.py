"""Per-user conversation pins using the existing authorised history database."""
import time
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from spia.api.access import require_access_context
from spia.security.access_control import AccessDenied
from spia.services import chat_history as h

router=APIRouter(prefix='/api/v1/conversations',tags=['Conversation pins'])

class PinRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    pinned: StrictBool
    revision: int=Field(ge=0)

def owner(context):
    i=context.identity
    return i.installation_id,i.company_id,i.user_id

def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS chat_pin (
        installation_id TEXT NOT NULL, company_id TEXT NOT NULL,
        user_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
        pinned_at INTEGER NOT NULL,
        PRIMARY KEY (installation_id,company_id,user_id,conversation_id),
        FOREIGN KEY (conversation_id) REFERENCES chat_master(id) ON DELETE CASCADE
    )""")

def list_pins(context):
    result=[]
    with h.connection(write=True) as db:
        schema(db)
        rows=db.execute("""SELECT p.conversation_id,p.pinned_at FROM chat_pin p
            JOIN chat_master c ON c.id=p.conversation_id AND c.deleted_at IS NULL
            WHERE p.installation_id=? AND p.company_id=? AND p.user_id=?
            ORDER BY p.pinned_at DESC,p.conversation_id""",owner(context)).fetchall()
        for pin in rows:
            try:
                row=h.row_for(db,context,pin['conversation_id'])
                h.authorize(context,row)
            except AccessDenied:
                continue
            except HTTPException as exc:
                if exc.status_code in (403,404):
                    continue
                raise
            result.append({
                **h.summary(row),
                'pinned':True,
                'pinned_at':pin['pinned_at'],
            })
    return {'conversations':result}

def set_pin(context,cid,pinned,revision):
    h.identifier(cid)
    with h.connection(write=True) as db:
        schema(db)
        row=h.row_for(db,context,cid)
        if pinned:
            try:
                h.authorize(context,row)
            except AccessDenied as exc:
                raise HTTPException(
                    403,'Current permissions do not allow this conversation.',
                    headers={'Cache-Control':'no-store'}
                ) from exc
        if row['revision']!=revision:
            raise HTTPException(
                409,'Conversation changed. Refresh and try again.',
                headers={'Cache-Control':'no-store'}
            )
        key=(*owner(context),cid)
        previous=db.execute("""SELECT pinned_at FROM chat_pin WHERE
            installation_id=? AND company_id=? AND user_id=? AND conversation_id=?""",key).fetchone()
        stamp=previous['pinned_at'] if previous else int(time.time()*1000)
        changed=bool(previous)!=pinned
        if pinned and not previous:
            db.execute('INSERT INTO chat_pin VALUES(?,?,?,?,?)',(*key,stamp))
        elif not pinned and previous:
            db.execute("""DELETE FROM chat_pin WHERE installation_id=? AND
                company_id=? AND user_id=? AND conversation_id=?""",key)
        if changed:
            db.execute('UPDATE chat_master SET revision=revision+1 WHERE id=?',(cid,))
        return {
            'id':cid,'pinned':pinned,
            'pinned_at':stamp if pinned else None,
            'revision':row['revision']+int(changed),
        }

@router.get('/pins')
def get_pins(response:Response,context=Depends(require_access_context)):
    response.headers['Cache-Control']='no-store'
    return list_pins(context)

@router.post('/{cid}/pin')
def pin_conversation(cid:str,body:PinRequest,response:Response,context=Depends(require_access_context)):
    response.headers['Cache-Control']='no-store'
    return set_pin(context,cid,body.pinned,body.revision)
