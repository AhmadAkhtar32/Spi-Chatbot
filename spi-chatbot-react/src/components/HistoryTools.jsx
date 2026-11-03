export function HistoryOlder({history}) {
  return history.older
    ? <button type="button" className="text-xs text-primary" onClick={()=>history.loadOlder().catch(e=>history.setError(e.message))}>Load earlier messages</button>
    : null
}
export default function HistoryTools({history:h}) {
  return <div className="space-y-2 py-2 text-xs">
    <input aria-label="Search chat history" placeholder="Search chats" maxLength={120} value={h.search} onChange={e=>h.setSearch(e.target.value)} className="w-full rounded-lg border border-border bg-bg px-3 py-2"/>
    {h.loading&&<p role="status">Loading conversation...</p>}
    {h.notice&&<p role="status" className="text-ink-secondary">{h.notice}</p>}
    {h.error&&<p role="alert" className="text-red-600">{h.error}</p>}
    {h.more&&<button type="button" className="text-primary" onClick={()=>h.loadMore().catch(e=>h.setError(e.message))}>Load more chats</button>}
  </div>
}
