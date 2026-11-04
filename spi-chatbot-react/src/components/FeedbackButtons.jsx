import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { ThumbsUp, ThumbsDown } from 'lucide-react'
import { API_BASE } from '../api/client.js'

let owner=null
const cache=new Map()

async function request(token,path,options={}){
  const response=await fetch(`${API_BASE}/api/v1/feedback/${path}`,{
    ...options,
    cache:'no-store',
    headers:{
      'Content-Type':'application/json',
      Authorization:`Bearer ${token}`,
    },
  })
  const data=await response.json().catch(()=>({}))
  if(!response.ok){
    throw new Error(typeof data.detail==='string'
      ?data.detail:`Feedback unavailable (${response.status}).`)
  }
  return data
}

function load(token,cid){
  if(owner!==token){cache.clear();owner=token}
  const old=cache.get(cid)
  if(old&&Date.now()-old.time<2000)return old.promise
  const promise=request(token,cid)
  cache.set(cid,{time:Date.now(),promise})
  return promise
}

export default function FeedbackButtons({messageId}){
  const {assistantSession,history,conversationId}=useOutletContext()||{}
  const token=assistantSession?.token
  const cid=conversationId||history?.active
  const persistent=history?.activeChat?.saved===true
  const [rating,setRating]=useState(null)
  const [busy,setBusy]=useState(false)
  const [ready,setReady]=useState(false)
  const [status,setStatus]=useState('')
  const live=useRef(false),version=useRef(0),writing=useRef(false)

  useEffect(()=>{
    let active=true
    live.current=true
    setRating(null);setBusy(false);setStatus('');setReady(!persistent)

    async function refresh(){
      if(!persistent||!token||!cid||!messageId)return
      const observed=version.current
      try{
        const data=await load(token,cid)
        if(active&&observed===version.current&&!writing.current){
          setRating(data.items.find(r=>r.message_id===messageId)?.rating||null)
          setReady(true)
          setStatus('')
        }
      }catch(e){
        if(active&&observed===version.current&&!writing.current){
          setReady(false)
          setStatus(e.message)
        }
      }
    }

    refresh()
    window.addEventListener('focus',refresh)
    return()=>{
      active=false
      live.current=false
      window.removeEventListener('focus',refresh)
    }
  },[token,cid,messageId,persistent])

  async function vote(next){
    if(busy||!ready||writing.current)return
    const value=rating===next?null:next
    if(!persistent){
      setRating(value)
      return
    }
    writing.current=true
    version.current++
    setBusy(true);setStatus('')
    try{
      const saved=await request(token,`${cid}/${messageId}`,{
        method:'POST',
        body:JSON.stringify({rating:value}),
      })
      if(owner===token)cache.delete(cid)
      if(live.current){
        setRating(saved.rating)
        setStatus(saved.rating?'Saved':'Removed')
      }
    }catch(e){
      if(live.current)setStatus(e.message)
    }finally{
      writing.current=false
      version.current++
      if(live.current)setBusy(false)
    }
  }

  return <span className="inline-flex min-w-0 flex-wrap items-center gap-1">
    {['up','down'].map(value=>{
      const Icon=value==='up'?ThumbsUp:ThumbsDown
      return <button key={value} type="button"
        aria-label={value==='up'?'Good response':'Poor response'}
        aria-pressed={rating===value}
        disabled={busy||!ready}
        onClick={()=>vote(value)}
        title={value==='up'?'Good response':'Poor response'}
        className={`h-7 w-7 rounded-full flex items-center justify-center disabled:opacity-40 ${rating===value?'bg-hover text-ink':'text-ink-secondary hover:bg-hover'}`}>
        {rating===value ? <span aria-hidden="true" style={{fontFamily:'"Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif',fontSize:18,lineHeight:1}}>{value==='up'?'\u{1F44D}\uFE0F':'\u{1F44E}\uFE0F'}</span> : <Icon className="h-3.5 w-3.5"/>}
      </button>
    })}
    <span role="status" className="ml-1 max-w-[220px] break-words text-[10px] text-ink-secondary">
      {!persistent?'Session only':busy?'Saving...':status||(!ready?'Loading...':'')}
    </span>
  </span>
}
