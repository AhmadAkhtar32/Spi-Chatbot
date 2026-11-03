import { useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE } from '../api/client.js'
import { businessAnswer } from './businessQuestions.js'

const id = () => {
  if (crypto.randomUUID) return crypto.randomUUID()
  const a=crypto.getRandomValues(new Uint8Array(16))
  a[6]=a[6]&15|64
  a[8]=a[8]&63|128
  const h=Array.from(a,n=>n.toString(16).padStart(2,'0')).join('')
  return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`
}
const fresh=(scope=null,manual=false)=>({id:id(),title:'New chat',scope,messages:[],manual})
const same=(a,b)=>a?.view===b?.view&&a?.expert===b?.expert&&a?.module===b?.module
const picture=data=>data?new File([Uint8Array.from(atob(data),c=>c.charCodeAt(0))],'screenshot.jpg',{type:'image/jpeg'}):null

function convert(row,scope){
  const p=row.payload||{}
  return {
    ...row,
    timestamp:row.created_at,
    content:p.kind?businessAnswer(p):p.reply||row.content,
    attachment:picture(row.image_base64),
    language:p.language,
    sources:(p.sources||[]).map(s=>p.source_labels?.[s]||s),
    raw_sources:p.sources||[],
    escalation:p.escalation,translation_proof:p.translation_proof,
    expert:scope.expert||'project_knowledge',
    module:scope.module||'project',
  }
}

export default function usePersonalHistory(session,expire){
  const token=session?.token
  const [chats,setChats]=useState([fresh()])
  const [active,setActive]=useState(null)
  const [enabled,setEnabled]=useState(null)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const [loading,setLoading]=useState(false)
  const [search,setSearch]=useState('')
  const [cursor,setCursor]=useState(null)
  const [older,setOlder]=useState(null)
  const [draft,setDraft]=useState(null)
  const realm=useRef(token)
  const live=useRef({})
  const epoch=useRef(0)
  const serial=useRef(0)
  const busy=useMemo(()=>({current:0}),[token])
  const locks=useMemo(()=>new Map(),[token])

  live.current={token,chats,active,enabled,search,cursor,older,expire}
  const scope=chats.find(c=>c.id===active)?.scope

  async function api(path,options={}){
    const owner=live.current.token
    if(!owner)throw new Error('Open the assistant first.')
    const response=await fetch(`${API_BASE}/api/v1/conversations${path}`,{
      ...options,
      cache:'no-store',
      headers:{
        'Content-Type':'application/json',
        ...options.headers,
        Authorization:`Bearer ${owner}`,
      },
    })
    const data=await response.json().catch(()=>({}))
    if(owner!==live.current.token)throw new Error('Session changed.')
    if(response.status===401){
      live.current.expire?.('Session expired. Please open the assistant again.')
    }
    if(!response.ok){
      throw Object.assign(
        new Error(typeof data.detail==='string'?data.detail:`History request failed (${response.status}).`),
        {status:response.status},
      )
    }
    return data
  }

  function newChat(next=scope,manual=true){
    epoch.current++
    const chat=fresh(next,manual)
    live.current.active=chat.id
    setChats(old=>[chat,...old.filter(c=>c.saved||c.messages.length)])
    setActive(chat.id)
    setOlder(null)
    setDraft(null)
    setError('')
    return chat
  }

  async function load(cid,before=2147483647,replace=false){
    const version=epoch.current
    const data=await api(`/${cid}/messages?before=${before}&limit=50`)
    if(version!==epoch.current||live.current.active!==cid||replace&&busy.current)return
    const mapped=data.messages.map(r=>convert(r,data.conversation.scope))
    const previous=live.current.chats.find(c=>c.id===cid)?.messages||[]
    const earlier=replace&&mapped.length&&previous.some(
      m=>Number.isInteger(m.sequence)&&m.sequence<mapped[0].sequence
    )
    setChats(old=>old.map(c=>c.id!==cid?c:{
      ...c,
      ...data.conversation,
      saved:true,
      messages:replace
        ? [...previous.filter(m=>mapped.length&&Number.isInteger(m.sequence)&&m.sequence<mapped[0].sequence),...mapped]
        : [...previous,...mapped.filter(m=>!previous.some(p=>p.id===m.id))].sort((a,b)=>a.sequence-b.sequence),
    }))
    setOlder(earlier?live.current.older:data.next_before)
  }

  async function selectChat(cid,supplied=null){
    const chat=supplied||live.current.chats.find(c=>c.id===cid)
    if(!chat)return
    epoch.current++
    live.current.active=cid
    setActive(cid)
    setDraft(null)
    setOlder(null)
    setError('')
    if(!chat.saved||live.current.enabled!==true)return
    setChats(old=>old.map(c=>c.id===cid?{...c,messages:[]}:c))
    if(chat.restricted){
      setError('Current permissions do not allow this conversation. You can delete it.')
      return
    }
    setLoading(true)
    try{await load(cid)}
    catch(e){setError(e.message)}
    finally{setLoading(false)}
  }

  function activateScope(next){
    const current=live.current.chats.find(c=>c.id===live.current.active)
    if(same(current?.scope,next))return
    const target=live.current.chats.find(c=>!c.restricted&&same(c.scope,next))
    if(target)selectChat(target.id).catch(e=>setError(e.message))
    else newChat(next,false)
  }

  async function refresh(append=false){
    if(!live.current.token||live.current.enabled!==true||busy.current)return
    const query=live.current.search,version=epoch.current,request=++serial.current
    const params=new URLSearchParams({q:query,limit:'20'})
    if(append&&live.current.cursor){params.set('before_time',live.current.cursor[0]);params.set('before_id',live.current.cursor[1])}
    try{
      const [data,pinData]=await Promise.all([api(`?${params}`),api('/pins')])
      if(request!==serial.current||version!==epoch.current||busy.current||query!==live.current.search)return
      const current=live.current.chats.find(c=>c.id===live.current.active)
      const pinMap=new Map(pinData.conversations.map(c=>[c.id,c]))
      const rows=data.conversations.map(c=>({...c,saved:true,pinned:pinMap.has(c.id),pinned_at:pinMap.get(c.id)?.pinned_at||null,messages:live.current.chats.find(p=>p.id===c.id)?.messages||[]}))
      const pins=query?[]:pinData.conversations.filter(c=>!rows.some(p=>p.id===c.id)).map(c=>({...c,saved:true,messages:live.current.chats.find(p=>p.id===c.id)?.messages||[]}))
      setCursor(data.next_cursor)
      setChats(old=>{
        const retained=old.map(c=>({...c,pinned:pinMap.has(c.id),pinned_at:pinMap.get(c.id)?.pinned_at||null}))
        const incoming=[...rows,...pins],byId=new Map(incoming.map(c=>[c.id,c]))
        const combined=append?[...retained.map(c=>byId.get(c.id)||c),...incoming]:[...incoming,...retained.filter(c=>!c.saved||c.id===live.current.active)]
        return combined.filter((c,i,all)=>all.findIndex(p=>p.id===c.id)===i)
      })
      if(current?.saved)await load(current.id,2147483647,true)
      else if(current&&!current.manual&&!current.messages.length){const target=rows.find(c=>!c.restricted&&same(c.scope,current.scope));if(target)await selectChat(target.id,target)}
      setError('')
    }catch(e){setChats(old=>old.map(c=>c.saved?{...c,messages:[]}:c));setError(e.message)}
  }
  useEffect(()=>{
    realm.current=token
    epoch.current++
    serial.current++
    const chat=fresh()
    live.current.active=chat.id
    setChats([chat])
    setActive(chat.id)
    setEnabled(null)
    setError('')
    setNotice('')
    setDraft(null)
    setOlder(null)
    setSearch('')
    let valid=true
    if(token){
      api('/status').then(s=>{
        if(valid){setEnabled(s.enabled);setNotice(s.notice||'')}
      }).catch(e=>{if(valid)setError(e.message)})
    }
    return()=>{valid=false}
  },[token])

  useEffect(()=>{
    if(enabled!==true)return
    const timer=setTimeout(()=>refresh(),250)
    return()=>clearTimeout(timer)
  },[enabled,search])

  useEffect(()=>{
    if(enabled!==true)return
    const tick=()=>{if(document.visibilityState==='visible')refresh()}
    const timer=setInterval(tick,15000)
    window.addEventListener('focus',tick)
    return()=>{
      clearInterval(timer)
      window.removeEventListener('focus',tick)
    }
  },[enabled,token,search])

  const boundId=active
  const boundToken=token

  function setMessages(updater){
    if(live.current.token!==boundToken)return
    setChats(old=>old.map(c=>{
      if(c.id!==boundId)return c
      const messages=typeof updater==='function'?updater(c.messages):updater
      return {
        ...c,
        messages,
        title:c.title==='New chat'
          ? messages.find(m=>m.role==='user')?.content?.slice(0,80)||c.title
          : c.title,
      }
    }))
  }

  async function prepare(next,question){
    if(live.current.enabled===false)return {}
    if(live.current.enabled!==true){
      throw new Error('History is still loading. Please try again.')
    }
    const chat=live.current.chats.find(c=>c.id===boundId)
    if(!chat||!same(chat.scope,next)){
      throw new Error('Conversation context changed. Please try again.')
    }
    if(!chat.saved){
      if(!locks.has(chat.id)){
        locks.set(chat.id,api('',{
          method:'POST',
          body:JSON.stringify({id:chat.id,scope:next}),
        }))
      }
      try{
        const saved=await locks.get(chat.id)
        setChats(old=>old.map(c=>c.id===chat.id?{...c,...saved,saved:true}:c))
      }finally{locks.delete(chat.id)}
    }
    if(live.current.token!==boundToken)throw new Error('Session changed.')
    return {
      'X-SPIA-Conversation':chat.id,
      'X-SPIA-Request-ID':id(),
      'X-SPIA-Question':btoa(String.fromCharCode(...new TextEncoder().encode(question))),
    }
  }

  function markResponse(data){
    if(live.current.token!==boundToken)return
    const r=data.history
    setChats(old=>old.map(c=>{
      if(c.id!==(r?.conversation_id||boundId))return c
      const messages=[...c.messages],a=messages.length-1,u=a-1
      if(messages[a]?.role==='assistant')messages[a]={
        ...messages[a],
        id:r?.answer_message_id||messages[a].id||id(),
        ...(r?{sequence:r.answer_sequence}:{}),
        escalation:data.escalation,
        escalation_proof:data.escalation_proof,
        raw_sources:data.sources||[],
        language:data.language||messages[a].language,
      }
      if(r&&messages[u]?.role==='user')messages[u]={
        ...messages[u],id:r.user_message_id,sequence:r.user_sequence,
      }
      return {...c,messages,revision:r?.revision??c.revision}
    }))
  }
  async function saveNotice(question,notice){
    if(enabled===false)return {reply:notice}
    const headers=await prepare({view:'business'},question)
    return api(`/${headers['X-SPIA-Conversation']}/notice`,{
      method:'POST',
      body:JSON.stringify({
        question,
        notice,
        request_id:headers['X-SPIA-Request-ID'],
      }),
    })
  }

  async function rename(cid=live.current.active){
    const chat=live.current.chats.find(c=>c.id===cid);if(!chat?.saved)return
    const title=window.prompt('Conversation title',chat.title);if(!title?.trim())return
    const saved=await api(`/${cid}/rename`,{method:'POST',body:JSON.stringify({title:title.trim(),revision:chat.revision})})
    setChats(old=>old.map(c=>c.id===cid?{...c,...saved}:c))
  }
  async function remove(cid=live.current.active){
    const chat=live.current.chats.find(c=>c.id===cid);if(!chat)return
    if(!window.confirm(`Delete "${chat.title}" from your history?`))return
    if(chat.saved)await api(`/${cid}/delete`,{method:'POST',body:'{}'})
    setChats(old=>old.filter(c=>c.id!==cid))
    if(live.current.active===cid)newChat(chat.scope)
  }
  async function togglePin(cid){
    const chat=live.current.chats.find(c=>c.id===cid);if(!chat?.saved)return
    const saved=await api(`/${cid}/pin`,{method:'POST',body:JSON.stringify({pinned:!chat.pinned,revision:chat.revision})})
    setChats(old=>old.map(c=>c.id===cid?{...c,...saved}:c))
    await refresh()
  }
  async function edit(messageId){
    const data=await api(`/${active}/fork`,{
      method:'POST',
      body:JSON.stringify({message_id:messageId}),
    })
    const chat={...data.conversation,messages:[],saved:true}
    epoch.current++
    live.current.active=chat.id
    setChats(old=>[chat,...old])
    setActive(chat.id)
    await load(chat.id)
    setDraft({
      text:data.draft,
      image:picture(data.image_base64),
      source:data.source,
    })
  }

  async function download(cid=live.current.active){
    const data=await api(`/${cid}/export`)
    const text=[data.conversation.title,...data.messages.map(r=>`${new Date(r.created_at).toISOString()} - ${r.role}\n${convert(r,data.conversation.scope).content}`)].join('\n\n')
    const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`conversation-${cid}.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  const visible=realm.current===token
  return {
    chats:visible?[...chats].sort((a,b)=>Number(!!b.pinned)-Number(!!a.pinned)||(b.pinned_at||0)-(a.pinned_at||0)):[],
    active:visible?active:null,
    scope:visible?scope:null,
    activeChat:visible?chats.find(c=>c.id===active):null,
    setMessages,newChat,selectChat,activateScope,prepare,markResponse,saveNotice,busy,
    error,setError,notice,loading,search,setSearch,rename,remove,togglePin,edit,download,draft,
    more:!!cursor,
    loadMore:()=>refresh(true),
    older:older!==null,
    loadOlder:()=>load(active,older),
  }
}
