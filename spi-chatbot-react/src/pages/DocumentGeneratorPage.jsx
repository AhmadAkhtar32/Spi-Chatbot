import { useEffect, useState } from 'react'
import { FileText, Download, Copy, Check, Loader2 } from 'lucide-react'
import Breadcrumb from '../layout/Breadcrumb.jsx'
import { API_BASE } from '../api.js'

export default function DocumentGeneratorPage() {
  const [templates, setTemplates] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [fieldValues, setFieldValues] = useState({})
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState(null) // { document_text, filename }
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/document-generator/templates`)
      .then((res) => res.json())
      .then((data) => {
        setTemplates(data.templates || [])
        if (data.templates?.length) setSelectedId(data.templates[0].id)
      })
      .catch(() => setError('Could not load templates. Confirm the backend is running.'))
  }, [])

  const selectedTemplate = templates.find((t) => t.id === selectedId)

  useEffect(() => {
    setFieldValues({})
    setResult(null)
  }, [selectedId])

  function updateField(key, value) {
    setFieldValues((prev) => ({ ...prev, [key]: value }))
  }

  async function handleGenerate(e) {
    e.preventDefault()
    setGenerating(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/document-generator/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_id: selectedId, fields: fieldValues }),
      })
      if (!res.ok) throw new Error('Generation failed')
      const data = await res.json()
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setGenerating(false)
    }
  }

  function handleCopy() {
    if (!result) return
    navigator.clipboard.writeText(result.document_text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  function handleDownload() {
    if (!result) return
    const blob = new Blob([result.document_text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = result.filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-8 py-8">
        <div className="mb-1">
          <Breadcrumb items={['Dashboard', 'Document Generator']} />
        </div>
        <h1 className="text-[19px] font-semibold text-ink mb-1">Document Generator</h1>
        <p className="text-[13.5px] text-ink-secondary mb-6 max-w-2xl leading-relaxed">
          Produces consistent, template-based deliverables. This fills a fixed template
          deterministically from the fields you provide — it does not use the AI model, since
          exact wording needs to stay identical every time a document is generated.
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Left: form */}
          <div className="card p-5">
            <label className="block text-[12.5px] font-medium text-ink-secondary mb-1.5">
              Document type
            </label>
            <select
              value={selectedId || ''}
              onChange={(e) => setSelectedId(e.target.value)}
              className="w-full h-9 px-2.5 mb-5 rounded-md border border-border bg-bg text-[13.5px] text-ink
                         focus:outline-none focus:border-primary"
            >
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>

            {selectedTemplate && (
              <form onSubmit={handleGenerate} className="flex flex-col gap-3.5">
                {selectedTemplate.fields.map((f) => (
                  <div key={f.key}>
                    <label className="block text-[12px] font-medium text-ink-secondary mb-1">
                      {f.label}
                    </label>
                    <input
                      type={f.type === 'date' ? 'date' : 'text'}
                      value={fieldValues[f.key] || ''}
                      onChange={(e) => updateField(f.key, e.target.value)}
                      required
                      className="w-full h-9 px-3 rounded-md border border-border bg-bg text-[13px] text-ink
                                 focus:outline-none focus:border-primary transition-colors"
                    />
                  </div>
                ))}

                <button
                  type="submit"
                  disabled={generating}
                  className="mt-2 h-9 rounded-md bg-primary text-white text-[13px] font-medium
                             hover:bg-primary-dark transition-colors disabled:opacity-50
                             flex items-center justify-center gap-2"
                >
                  {generating ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" /> Generating...
                    </>
                  ) : (
                    <>
                      <FileText className="w-3.5 h-3.5" /> Generate document
                    </>
                  )}
                </button>
                {error && <p className="text-[12.5px] text-danger">{error}</p>}
              </form>
            )}
          </div>

          {/* Right: preview */}
          <div className="card p-5 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-[13px] font-semibold text-ink">Preview</h2>
              {result && (
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={handleCopy}
                    className="w-7 h-7 rounded-md flex items-center justify-center text-ink-secondary hover:bg-slate-50 hover:text-ink transition-colors"
                    title="Copy"
                  >
                    {copied ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    onClick={handleDownload}
                    className="w-7 h-7 rounded-md flex items-center justify-center text-ink-secondary hover:bg-slate-50 hover:text-ink transition-colors"
                    title="Download"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>

            {result ? (
              <pre className="flex-1 bg-bg border border-border rounded-md p-4 text-[12px] font-mono text-ink whitespace-pre-wrap overflow-auto">
                {result.document_text}
              </pre>
            ) : (
              <div className="flex-1 flex items-center justify-center text-center py-10">
                <p className="text-[12.5px] text-ink-secondary/70 max-w-xs">
                  Fill in the fields on the left and generate a document to see the preview here.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}