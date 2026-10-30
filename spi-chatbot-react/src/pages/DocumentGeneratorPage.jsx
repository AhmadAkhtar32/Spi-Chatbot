import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { FileText, Download, Copy, Loader2 } from 'lucide-react'
import Breadcrumb from '../layout/Breadcrumb.jsx'
import { API_BASE } from '../api/client.js'

export default function DocumentGeneratorPage({ templates = [] }) {
  const { assistantSession, switchAssistantUser } = useOutletContext()
  const token = assistantSession?.token
  const [selectedId, setSelectedId] = useState(templates[0]?.id || '')
  const [recordId, setRecordId] = useState('')
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [pdfUrl, setPdfUrl] = useState('')
  const pending = useRef(null)
  const selected = templates.find(template => template.id === selectedId)
  const preview = result?.token === token && selected ? result : null

  useEffect(() => {
    if (!preview?.pdf_base64) {
      setPdfUrl('')
      return
    }

    let url

    try {
      const raw = atob(preview.pdf_base64)

      if (!raw.startsWith('%PDF-')) {
        throw new Error('Invalid PDF')
      }

      const bytes = Uint8Array.from(
        raw,
        character => character.charCodeAt(0)
      )

      url = URL.createObjectURL(
        new Blob([bytes], { type: 'application/pdf' })
      )

      setPdfUrl(url)
    } catch {
      setPdfUrl('')
      setError(
        'The server did not return a valid PDF. Restart the updated backend and generate again.'
      )
    }

    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [preview?.pdf_base64, token])

  useEffect(() => () => pending.current?.abort(), [])

  useEffect(() => {
    if (!templates.some(template => template.id === selectedId)) {
      pending.current?.abort()
      setSelectedId(templates[0]?.id || '')
      setResult(null)
      setRecordId('')
      setGenerating(false)
    }
  }, [templates, selectedId])

  function changeTemplate(value) {
    pending.current?.abort()
    setSelectedId(value)
    setRecordId('')
    setResult(null)
    setError('')
    setGenerating(false)
  }

  async function generate(event) {
    event.preventDefault()
    if (generating || !selected || !token) return

    const id = recordId.trim()
    setResult(null)
    setError('')

    if (!/^[A-Za-z0-9-]{1,64}$/.test(id)) {
      setError('Enter a valid source record ID.')
      return
    }

    const controller = new AbortController()
    pending.current = controller
    setGenerating(true)

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/documents/generate`,
        {
          method: 'POST',
          cache: 'no-store',
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            template_id: selected.id,
            record_id: id,
          }),
        }
      )

      if (response.status === 401) {
        switchAssistantUser(
          'Session expired. Please open the assistant again.'
        )
        return
      }
      if (response.status === 403) {
        throw new Error(
          'You are not authorized to generate this document or its required fields.'
        )
      }
      if (response.status === 404) {
        throw new Error(
          'The source record was not found or is unavailable to you.'
        )
      }
      if (!response.ok) {
        throw new Error(
          'The document could not be generated. Please try again.'
        )
      }

      const document = await response.json()
      if (
        typeof document.document_text !== 'string' ||
        typeof document.pdf_base64 !== 'string' ||
        !document.filename?.endsWith('.pdf') ||
        document.template_id !== selected.id ||
        document.record_id !== id
      ) {
        throw new Error('The server returned an unexpected document.')
      }

      if (!controller.signal.aborted) {
        setResult({ ...document, token })
      }
    } catch (failure) {
      if (!controller.signal.aborted) {
        setError(failure.message || 'Could not connect to the server.')
      }
    } finally {
      if (!controller.signal.aborted) setGenerating(false)
    }
  }

  async function copy() {
    if (!preview) return
    try {
      await navigator.clipboard.writeText(preview.document_text)
      setError('')
    } catch {
      setError(
        'Copy failed. You can select the preview text or download the document.'
      )
    }
  }

  function download() {
    if (!preview || !pdfUrl) return

    const link = document.createElement('a')
    link.href = pdfUrl
    link.download = preview.filename
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-4 sm:px-8 py-8">
        <Breadcrumb items={['Dashboard', 'Document Generator']} />
        <h1 className="text-[19px] font-semibold text-ink mt-2 mb-1">
          Document Generator
        </h1>
        <p className="text-[13.5px] text-ink-secondary mb-6">
          Choose a template and enter its source record ID. The document
          uses the values you are permitted to access.
        </p>

        <div className="flex flex-col gap-5">
          <form onSubmit={generate} className="card p-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_auto] items-end">
            <label className="text-sm">
              Document type
              <select
                value={selected?.id || ''}
                disabled={generating || !templates.length}
                onChange={event => changeTemplate(event.target.value)}
                className="mt-2 w-full rounded-md border border-border bg-bg px-3 py-2"
              >
                {templates.map(template => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="text-sm">
              Source record ID
              <input
                value={recordId}
                required
                maxLength={64}
                disabled={generating || !selected}
                placeholder={
                  selectedId === 'purchase_order'
                    ? 'Enter purchase order ID'
                    : 'Enter credit/return note ID'
                }
                onChange={event => {
                  setRecordId(event.target.value)
                  setResult(null)
                  setError('')
                }}
                className="mt-2 w-full rounded-md border border-border bg-bg px-3 py-2"
              />
            </label>

            <button
              type="submit"
              disabled={generating || !selected || !recordId.trim()}
              className="rounded-md bg-primary text-white px-4 py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {generating
                ? <Loader2 size={16} className="animate-spin" />
                : <FileText size={16} />}
              {generating ? 'Generating…' : 'Generate document'}
            </button>

            {error && (
              <p role="alert" className="text-sm text-danger sm:col-span-2 lg:col-span-3">
                {error}
              </p>
            )}
          </form>

          <section className="card p-5 flex flex-col min-w-0">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold">PDF preview</h2>
              {preview && (
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={copy}
                    aria-label="Copy document"
                    title="Copy document"
                  >
                    <Copy size={16} />
                  </button>
                  <button
                    type="button"
                    onClick={download}
                    disabled={!pdfUrl}
                    className="flex items-center gap-1 disabled:opacity-50"
                    aria-label="Download PDF"
                    title="Download PDF"
                  >
                    <Download size={16} />
                    <span className="text-xs ml-1">PDF</span>
                  </button>
                </div>
              )}
            </div>

            {preview ? (
              <>
                <p className="text-xs text-ink-secondary mb-2">
                  Source: {preview.record_id}
                </p>
                {pdfUrl && (
                  <div className="space-y-3">
                    <a
                      href={pdfUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block text-sm text-primary underline"
                    >
                      Open PDF to print
                    </a>

                    <iframe
                      title="Generated PDF preview"
                      src={pdfUrl}
                      className="block w-full max-w-[794px] mx-auto h-[70vh] min-h-[360px] rounded-md border border-border bg-white"
                    />
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-ink-secondary py-10 text-center">
                Generate a document to see its original template here.
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}