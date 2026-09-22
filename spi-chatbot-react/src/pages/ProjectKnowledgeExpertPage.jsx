import { useEffect, useRef, useState } from 'react'
import { Upload, FileText, Loader2 } from 'lucide-react'
import Breadcrumb from '../layout/Breadcrumb.jsx'
import ChatMessage from '../components/ChatMessage.jsx'
import TypingIndicator from '../components/TypingIndicator.jsx'
import MessageInput from '../components/MessageInput.jsx'
import { API_BASE } from '../api.js'

const DEMO_CLIENTS = ['demo_client', 'client_acme_corp', 'client_northstar']

export default function ProjectKnowledgeExpertPage() {
  const [clientId, setClientId] = useState('demo_client')
  const [documents, setDocuments] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)

  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const fileInputRef = useRef(null)
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  // Refetch this client's document list whenever the selected client changes.
  useEffect(() => {
    setMessages([])
    refreshDocuments(clientId)
  }, [clientId])

  async function refreshDocuments(id) {
    try {
      const res = await fetch(`${API_BASE}/api/project-knowledge/documents?client_id=${encodeURIComponent(id)}`)
      const data = await res.json()
      setDocuments(data.documents || [])
    } catch {
      setDocuments([])
    }
  }

  async function handleFileSelected(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadError(null)

    if (!file.name.toLowerCase().endsWith('.txt')) {
      setUploadError('Only .txt files are supported right now.')
      e.target.value = ''
      return
    }

    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('client_id', clientId)
      formData.append('file', file)
      const res = await fetch(`${API_BASE}/api/project-knowledge/upload`, { method: 'POST', body: formData })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Upload failed')
      }
      await refreshDocuments(clientId)
    } catch (err) {
      setUploadError(err.message)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  async function handleSend(text) {
    setMessages((prev) => [...prev, { role: 'user', content: text, timestamp: Date.now() }])
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/project-knowledge/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId, question: text }),
      })
      const data = await res.json()
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.reply, sources: data.sources, timestamp: Date.now() },
      ])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Unable to reach the backend service. Confirm the API server is running.',
          timestamp: Date.now(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  function handleClear() {
    setMessages([])
  }

  const hasMessages = messages.length > 0

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-6 pt-4 pb-3 border-b border-border bg-surface">
        <Breadcrumb items={['Dashboard', 'Project Knowledge Expert']} />
        <h1 className="text-[17px] font-semibold text-ink">Project Knowledge Expert</h1>
        <p className="text-[13px] text-ink-secondary mt-0.5">
          Customer-specific documents, decisions, and history — scoped to one client at a time.
        </p>
      </div>

      {/* Client selector + upload */}
      <div className="px-6 py-3 border-b border-border bg-surface flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label className="text-[12.5px] font-medium text-ink-secondary">Client:</label>
          <select
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            className="h-8 px-2.5 rounded-md border border-border bg-bg text-[12.5px] text-ink
                       focus:outline-none focus:border-primary"
          >
            {DEMO_CLIENTS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        <div className="w-px h-5 bg-border" />

        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-1.5 h-8 px-3 rounded-md border border-border text-[12.5px]
                     font-medium text-ink hover:bg-slate-50 transition-colors disabled:opacity-50"
        >
          {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
          {uploading ? 'Uploading...' : 'Upload document (.txt)'}
        </button>
        <input ref={fileInputRef} type="file" accept=".txt" onChange={handleFileSelected} className="hidden" />

        <div className="flex flex-wrap items-center gap-1.5">
          {documents.length === 0 && (
            <span className="text-[12px] text-ink-secondary/70">No documents uploaded for this client yet</span>
          )}
          {documents.map((d) => (
            <span
              key={d}
              className="flex items-center gap-1 text-[11px] font-mono text-ink-secondary bg-bg border border-border rounded px-1.5 py-0.5"
            >
              <FileText className="w-3 h-3" />
              {d}
            </span>
          ))}
        </div>

        {uploadError && <span className="text-[12px] text-danger">{uploadError}</span>}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6 flex flex-col gap-4">
          {!hasMessages && (
            <div className="card p-4 text-[12.5px] text-ink-secondary leading-relaxed">
              Upload a document for <span className="font-medium text-ink">{clientId}</span>, then
              ask a question about it — this expert only ever searches documents belonging to the
              selected client, never another client's files.
            </div>
          )}

          {messages.map((m, i) => (
            <ChatMessage
              key={i}
              role={m.role}
              content={m.content}
              sources={m.sources}
              timestamp={m.timestamp}
            />
          ))}
          {loading && <TypingIndicator />}
        </div>
      </div>

      <MessageInput
        onSend={handleSend}
        disabled={loading}
        value={inputValue}
        onValueChange={setInputValue}
        onClear={handleClear}
        hasMessages={hasMessages}
      />
    </div>
  )
}