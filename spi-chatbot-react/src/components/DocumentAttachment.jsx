
import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { FileText, Download, Loader2 } from 'lucide-react'
import { API_BASE } from '../api/client.js'

export default function DocumentAttachment({ attachment }) {
  const { assistantSession } = useOutletContext() || {}
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const request = useRef(null), token = assistantSession?.token
  useEffect(() => {
    setBusy(false); setError('')
    return () => { request.current?.abort(); request.current = null }
  }, [attachment, token])
  const local = attachment instanceof Blob
  const filename = local ? attachment.name || 'Document' : attachment.filename
  const size = attachment.size || 0
  async function download() {
    if (request.current) return
    const controller = new AbortController(); request.current = controller
    setBusy(true); setError('')
    let timer
    try {
      timer = setTimeout(() => controller.abort(), 20000)
      let file = attachment
      if (!local) {
        const response = await fetch(`${API_BASE}/api/v1/conversations/${attachment.conversation_id}/attachments/${attachment.message_id}`, {
          cache: 'no-store', signal: controller.signal,
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!response.ok) {
          const data = await response.json().catch(() => ({}))
          throw new Error(typeof data.detail === 'string' ? data.detail : 'Attachment is unavailable.')
        }
        file = await response.blob()
      }
      if (controller.signal.aborted || request.current !== controller) return
      const url = URL.createObjectURL(file), link = document.createElement('a')
      link.href = url; link.download = filename; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      if (request.current === controller) setError(e.name === 'AbortError' ? 'Download timed out. Try again.' : e.message)
    } finally {
      clearTimeout(timer)
      if (request.current === controller) { request.current = null; setBusy(false) }
    }
  }
  return <div className="mb-2 rounded-lg border border-border bg-surface p-3 whitespace-normal">
    <button type="button" onClick={download} disabled={busy} aria-label={`Download ${filename}`}
      className="flex w-full items-center gap-2 text-start disabled:opacity-50">
      <FileText className="h-6 w-6 shrink-0 text-primary" />
      <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{filename}</span>
        <span className="block text-xs text-ink-secondary">Document attached - {Math.ceil(size / 1024)} KB</span></span>
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
    </button>
    {error && <p role="alert" className="mt-2 text-xs text-danger">{error}</p>}
  </div>
}
