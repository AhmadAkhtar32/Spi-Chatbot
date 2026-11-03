import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { MessageCircle, Loader2 } from 'lucide-react'
import { API_BASE } from '../api/client.js'

export default function EscalationActions({messageId}) {
  const context=useOutletContext()||{}
  const {assistantSession,history,messages=[],conversationId,switchAssistantUser}=context
  const token=assistantSession?.token
  const item=messages.find(m=>m.id===messageId)
  const [data,setData]=useState(null),[team,setTeam]=useState('')
  const [busy,setBusy]=useState(false),[error,setError]=useState('')
  const pending=useRef(null)

  useEffect(()=>{
    setData(null);setTeam('');setError('');setBusy(false)
    return()=>{
      const request=pending.current
      pending.current=null
      request?.abort()
    }
  },[token,conversationId,messageId])

  if(!token||!messageId||!item?.escalation?.eligible)return null

  async function review(){
    if(busy)return
    const controller=new AbortController()
    pending.current=controller
    const timer=setTimeout(()=>controller.abort(),15000)
    setBusy(true);setError('')
    try{
      const saved=history?.activeChat?.saved===true
      let body={
        conversation_id:conversationId||history?.active,
        message_id:messageId,
      }
      if(!saved){
        const index=messages.findIndex(m=>m.id===messageId)
        const question=messages[index-1]
        if(!item.escalation_proof||question?.role!=='user'){
          throw new Error('Ask the question again after the updated backend is deployed.')
        }
        const scope=history?.scope
        body={
          expert:scope?.view==='company'?'project_knowledge':scope?.expert,
          module:scope?.module,
          reply:item.content,
          language:item.language||'en',
          sources:item.raw_sources||[],
          question:question.content,
          has_image:!!question.attachment,
          proof:item.escalation_proof,
        }
      }
      const response=await fetch(
        `${API_BASE}/api/v1/escalations/${saved?'prepare':'prepare-live'}`,
        {
          method:'POST',cache:'no-store',signal:controller.signal,
          headers:{
            'Content-Type':'application/json',
            Authorization:`Bearer ${token}`,
          },
          body:JSON.stringify(body),
        }
      )
      if(response.status===401){
        switchAssistantUser?.('Session expired. Please open the assistant again.')
        return
      }
      const result=await response.json().catch(()=>({}))
      if(!response.ok){
        throw new Error(typeof result.detail==='string'
          ?result.detail:'Could not prepare WhatsApp contact.')
      }
      if(!controller.signal.aborted){
        setData(result)
        setTeam(result.recommended||'')
      }
    }catch(e){
      if(!controller.signal.aborted)setError(e.message)
      else if(pending.current===controller)setError('Contact request timed out. Please try again.')
    }finally{
      clearTimeout(timer)
      if(pending.current===controller){
        pending.current=null
        setBusy(false)
      }
    }
  }

  const options=data?.contacts?.filter(c=>c.department===team)||[]

  return <div className="mt-3 rounded-xl border border-border bg-bg p-3 text-sm">
    <button type="button" disabled={busy} onClick={review} className="flex items-center gap-2 font-medium text-primary disabled:opacity-50">
      {busy?<Loader2 className="h-4 w-4 animate-spin"/>:<MessageCircle className="h-4 w-4"/>}
      {busy?'Preparing contact...':'Contact team on WhatsApp'}
    </button>
    {error&&<p role="alert" className="mt-2 text-xs text-red-600">{error}</p>}
    {data&&<div className="mt-3 space-y-3">
      <label className="block text-xs text-ink-secondary">
        {data.recommended?'Recommended team':'Choose the team'}
        <select aria-label="WhatsApp team" value={team} onChange={e=>setTeam(e.target.value)} className="mt-1 block w-full rounded-lg border border-border bg-surface px-2 py-2 text-sm text-ink">
          <option value="">Select a team</option>
          <option value="support">Support</option>
          <option value="implementation">Implementation</option>
        </select>
      </label>
      {team&&<>
        <details>
          <summary className="cursor-pointer text-xs text-ink-secondary">Review the message before sharing</summary>
          <pre dir="auto" className="mt-2 whitespace-pre-wrap break-words rounded-lg bg-surface p-3 font-sans text-xs leading-relaxed">{data.messages[team]}</pre>
        </details>
        {options.length
          ?options.map(c=><a key={c.id} href={c.url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" className="inline-flex items-center gap-2 mr-2 rounded-lg bg-[#128c4a] px-3 py-2 text-xs font-medium text-white"><MessageCircle className="h-4 w-4"/>{c.name}</a>)
          :<p role="status" className="text-xs text-ink-secondary">No WhatsApp contact is configured for this team. Ask your administrator to add one.</p>
        }
        <p className="text-xs text-ink-secondary">
          WhatsApp opens with your question filled in. Review it and press Send.
          {data.has_image?' Attach the screenshot manually in WhatsApp.':''}
        </p>
      </>}
    </div>}
  </div>
}
