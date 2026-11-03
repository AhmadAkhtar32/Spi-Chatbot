"""Prepare WhatsApp links from a freshly authorised, saved question."""
import json
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from spia.api.access import require_access_context
from spia.security.access_control import AccessDenied
from spia.services import chat_history as h
from spia.services import escalation as e

router=APIRouter(prefix='/api/v1/escalations',tags=['WhatsApp escalation'])

class PrepareRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    conversation_id:str=Field(min_length=36,max_length=36)
    message_id:str=Field(min_length=36,max_length=36)

def deny(status,text):
    raise HTTPException(status,text,headers={'Cache-Control':'no-store'})

def prepare(context,cid,mid):
    h.identifier(cid)
    h.identifier(mid)
    try:
        with h.connection() as db:
            row=h.row_for(db,context,cid)
            h.authorize(context,row)
            scope=json.loads(row['scope'])
            if scope.get('view') not in ('knowledge','company'):
                deny(409,'This is not a document-expert conversation.')
            answer=db.execute(
                "SELECT * FROM chat_message WHERE id=? AND conversation_id=? AND role='assistant'",
                (mid,cid)
            ).fetchone()
            if answer is None:
                deny(404,'Answer not found')
            payload=json.loads(answer['payload'] or '{}')
            if not e.eligible(
                payload.get('reply',answer['content']),payload.get('escalation')
            ):
                deny(409,'This answer is not marked as missing knowledge.')
            question=db.execute(
                "SELECT * FROM chat_message WHERE conversation_id=? AND sequence=? AND role='user'",
                (cid,answer['sequence']-1)
            ).fetchone()
            if question is None:
                deny(404,'Question not found')
            recommended,reason=e.department(
                question['content'],scope.get('expert')
            )
            contacts=e.load_contacts(context)
            reference=cid[:8]+'/'+mid[:8]
            messages={
                team:e.message(
                    question['content'],scope.get('module','project'),
                    team,reference,payload.get('language')=='ur',
                    bool(question['image'])
                )
                for team in e.TEAMS
            }
            options=[
                {
                    'id':c.id,'name':c.name,'department':c.department,
                    'url':e.whatsapp_url(c.phone,messages[c.department]),
                }
                for c in contacts
            ]
            h.authorize(context,row)
            return {
                'recommended':recommended,'routing_reason':reason,
                'contacts':options,'messages':messages,
                'has_image':bool(question['image']),
            }
    except AccessDenied:
        deny(403,'Current permissions do not allow this conversation.')
    except ValueError:
        deny(503,'WhatsApp contacts need administrator configuration.')

@router.post('/prepare')
def prepare_escalation(body:PrepareRequest,response:Response,context=Depends(require_access_context)):
    response.headers['Cache-Control']='no-store'
    return prepare(context,body.conversation_id,body.message_id)
