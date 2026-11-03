import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { MessageSquareText, MoreHorizontal, Pin, PencilLine, Download, Trash2 } from 'lucide-react'

export default function HistoryRow({conversation:c,active,collapsed,onSelect,history:h}) {
  const [open,setOpen]=useState(false)
  const [busy,setBusy]=useState(false)
  const [position,setPosition]=useState({top:0,left:0})
  const trigger=useRef(null),menu=useRef(null)
  const title=c.title||'New chat'
  const close=(focus=false)=>{setOpen(false);if(focus)trigger.current?.focus()}

  useEffect(()=>{
    if(!open)return
    const outside=e=>{
      if(!menu.current?.contains(e.target)&&!trigger.current?.contains(e.target))close()
    }
    const escape=e=>{
      if(e.key==='Escape'){e.preventDefault();close(true)}
    }
    const hide=()=>close()
    const scroll=e=>{if(!menu.current?.contains(e.target))close()}
    document.addEventListener('pointerdown',outside)
    document.addEventListener('keydown',escape)
    window.addEventListener('resize',hide)
    window.addEventListener('scroll',scroll,true)
    menu.current?.querySelector('[role="menuitem"]')?.focus()
    return()=>{
      document.removeEventListener('pointerdown',outside)
      document.removeEventListener('keydown',escape)
      window.removeEventListener('resize',hide)
      window.removeEventListener('scroll',scroll,true)
    }
  },[open])

  function toggle(){
    if(open){close(true);return}
    const r=trigger.current.getBoundingClientRect()
    const height=c.restricted?56:176
    setPosition({
      left:Math.max(8,Math.min(r.right-184,window.innerWidth-192)),
      top:Math.max(8,Math.min(r.bottom+5,window.innerHeight-height-8)),
    })
    setOpen(true)
  }

  async function action(fn){
    if(busy)return
    setBusy(true)
    close(true)
    try{await fn(c.id)}
    catch(e){h.setError(e.message)}
    finally{setBusy(false)}
  }

  function keys(e){
    const buttons=[...menu.current.querySelectorAll('[role="menuitem"]')]
    const current=buttons.indexOf(document.activeElement)
    let next
    if(e.key==='ArrowDown')next=(current+1)%buttons.length
    if(e.key==='ArrowUp')next=(current-1+buttons.length)%buttons.length
    if(e.key==='Home')next=0
    if(e.key==='End')next=buttons.length-1
    if(next!==undefined){e.preventDefault();buttons[next]?.focus()}
    if(e.key==='Tab')close()
  }

  const items=[
    ...(!c.restricted?[
      {label:c.pinned?'Unpin chat':'Pin chat',icon:Pin,run:h?.togglePin},
      {label:'Rename',icon:PencilLine,run:h?.rename},
      {label:'Export',icon:Download,run:h?.download},
    ]:[]),
    {label:'Delete',icon:Trash2,run:h?.remove,danger:true},
  ]

  return <div className={`group flex items-center rounded-lg ${active?'bg-primary/10 text-primary':'text-ink-secondary hover:bg-hover hover:text-ink'}`}>
    <button type="button" onClick={()=>onSelect(c.id)} title={title} className="flex min-w-0 flex-1 items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[13.5px] font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
      <MessageSquareText className="h-4 w-4 shrink-0" strokeWidth={2}/>
      <span className={`min-w-0 flex-1 truncate ${collapsed?'md:hidden':''}`}>{title}</span>
      {c.pinned&&<Pin aria-label="Pinned chat" className={`h-3 w-3 shrink-0 ${collapsed?'md:hidden':''}`}/>}
    </button>
    {h&&c.saved&&<button ref={trigger} type="button" aria-label={`Chat actions: ${title}`} aria-haspopup="menu" aria-expanded={open} disabled={busy} onClick={toggle} className={`mr-1 shrink-0 rounded-md p-1.5 hover:bg-primary/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary disabled:opacity-40 ${collapsed?'md:hidden':''} ${active||open?'':'md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100'}`}>
      <MoreHorizontal className="h-4 w-4"/>
    </button>}
    {open&&createPortal(
      <div ref={menu} role="menu" aria-label={`Actions for ${title}`} onKeyDown={keys} style={{position:'fixed',...position,width:184,zIndex:1000}} className="rounded-xl border border-border bg-surface p-1.5 text-sm text-ink shadow-xl">
        {items.map(({label,icon:Icon,run,danger})=>
          <button key={label} role="menuitem" type="button" onClick={()=>action(run)} className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left hover:bg-hover focus:bg-hover focus:outline-none ${danger?'text-red-600':''}`}>
            <Icon className="h-4 w-4"/>{label}
          </button>
        )}
      </div>,document.body
    )}
  </div>
}
