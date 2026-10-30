import { useEffect, useRef, useState } from 'react'
import { Copy, Check, Download, RotateCcw, ThumbsUp, ThumbsDown, Languages, Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { API_BASE } from '../api/client.js'

function CodeRenderer({ className, children }) {
  return <code dir="ltr" className={className} style={{ unicodeBidi: 'isolate' }}>{children}</code>
}

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function ChatMessage({ attachment, role, content, trace, sources, timestamp, onRegenerate, isLast, language, translation }) {
  const [copied, setCopied] = useState(false)
  const [feedback, setFeedback] = useState(null) // 'up' | 'down' | null
  const [attachmentUrl, setAttachmentUrl] = useState('')
  const attachmentDialog = useRef(null)
  useEffect(() => {
    if (!(attachment instanceof Blob)) { setAttachmentUrl(''); return }
    const url = URL.createObjectURL(attachment)
    setAttachmentUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [attachment])
  const isUser = role === 'user'
  const time = timestamp ? formatTime(new Date(timestamp)) : null

  const originalLanguage = language || (/[\u0600-\u06ff]/.test(content) ? 'ur' : 'en')
  const [translationState, setTranslationState] = useState(null)
  const [translating, setTranslating] = useState(false)
  const [translationError, setTranslationError] = useState('')
  const pendingTranslation = useRef(null)
  const shownContent = translationState?.reply || content
  const shownLanguage = translationState?.language || originalLanguage
  const targetLanguage = shownLanguage === 'ur' ? 'en' : 'ur'

  useEffect(() => {
    setTranslationState(null)
    setTranslationError('')
    setTranslating(false)
    return () => {
      pendingTranslation.current?.abort()
      pendingTranslation.current = null
    }
  }, [translation?.token, translation?.proof, content])

  async function translateAnswer() {
    if (!translation?.token || !translation.proof || pendingTranslation.current) return

    const controller = new AbortController()
    pendingTranslation.current = controller
    let timedOut = false

    const timeout = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, 45000)

    setTranslating(true)
    setTranslationError('')

    try {
      const response = await fetch(`${API_BASE}/api/v1/experts/translate`, {
        method: 'POST',
        cache: 'no-store',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${translation.token}`,
        },
        body: JSON.stringify({
          expert: translation.expert,
          module: translation.module,
          original_text: content,
          original_language: originalLanguage,
          target_language: targetLanguage,
          sources: translation.sources,
          proof: translation.proof,
        }),
      })

      if (pendingTranslation.current !== controller) return

      if (response.status === 401) {
        translation.onSessionExpired?.('Session expired. Please open the assistant again.')
        throw new Error('Session expired. Please open the assistant again.')
      }

      if (response.status === 403) {
        throw new Error('This answer is no longer available for translation. Please ask it again or check your access.')
      }

      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Translation is unavailable.')
      }

      if (typeof data.reply !== 'string' || data.language !== targetLanguage) {
        throw new Error('Translation returned an unexpected response.')
      }

      if (pendingTranslation.current === controller && !controller.signal.aborted) {
        setTranslationState(data)
      }
    } catch (error) {
      if (pendingTranslation.current === controller) {
        setTranslationError(
          timedOut ? 'Translation timed out. Please try again.' : error.message
        )
      }
    } finally {
      clearTimeout(timeout)
      if (pendingTranslation.current === controller) {
        pendingTranslation.current = null
        setTranslating(false)
      }
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(shownContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  function handleExport() {
    const blob = new Blob([shownContent], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `spi-response-${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (isUser) {
    return (
      <div className="flex flex-col items-end animate-fade-in min-w-0">
        <div dir="auto" style={originalLanguage === 'ur' ? { fontFamily: '"Noto Naskh Arabic", "Segoe UI", Tahoma, Arial, sans-serif', fontSize: '16px', lineHeight: 1.9 } : undefined} className="max-w-[88%] sm:max-w-[75%] min-w-0 bg-primary/8 border border-primary/15 rounded-lg px-3.5 sm:px-4 py-2.5 text-[14px] text-ink whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
          {attachmentUrl && <>
            <button type="button" onClick={() => attachmentDialog.current?.showModal()}
              aria-label="View attached screenshot" className="block mb-2 max-w-full text-start">
              <img src={attachmentUrl} alt="Attached screenshot" className="block max-w-full w-60 max-h-40 object-contain rounded-lg border border-border bg-surface" />
              <span className="block mt-1 text-xs text-ink-secondary">Screenshot attached - click to enlarge</span>
            </button>
            <dialog ref={attachmentDialog} aria-label="Attached screenshot preview"
              onClick={event => { if (event.target === event.currentTarget) event.currentTarget.close() }}
              className="m-auto max-w-[95vw] max-h-[95dvh] rounded-xl border border-border bg-surface p-3 text-ink backdrop:bg-black/70">
              <div className="flex justify-end mb-2">
                <button type="button" onClick={() => attachmentDialog.current?.close()}
                  className="rounded-lg border border-border px-3 py-1 text-sm">Close preview</button>
              </div>
              <img src={attachmentUrl} alt="Enlarged attached screenshot" className="block max-w-[90vw] max-h-[80dvh] object-contain" />
            </dialog>
          </>}
          {content}
        </div>
        {time && <span className="text-[11px] text-ink-secondary/70 mt-1 mr-0.5">{time}</span>}
      </div>
    )
  }

  return (
    <div className="flex flex-col items-start animate-fade-in min-w-0">
      <div className="max-w-[96%] sm:max-w-[85%] lg:max-w-[80%] min-w-0 group relative card px-3.5 sm:px-4 py-3">
        {trace && trace.length > 0 && (
          <div className="text-[11px] font-mono text-ink-secondary/80 mb-2 pb-2 border-b border-border break-words">
            {trace.join(', ')}
          </div>
        )}
        <div className="assistant-markdown" dir={shownLanguage === 'ur' ? 'rtl' : 'ltr'} lang={shownLanguage}
          style={shownLanguage === 'ur' ? { textAlign: 'right', fontFamily: '"Noto Naskh Arabic", "Segoe UI", Tahoma, Arial, sans-serif', fontSize: '16px', lineHeight: 1.9 } : undefined}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeRenderer }}>
            {shownContent}
          </ReactMarkdown>
        </div>

        {sources && sources.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 mt-2.5 pt-2.5 border-t border-border">
            <span className="text-[10.5px] font-medium text-ink-secondary/70 uppercase tracking-wide mr-0.5">
              Sources
            </span>
            {sources.map((s) => (
              <span
                key={s}
                className="text-[11px] font-mono text-ink-secondary bg-bg border border-border rounded px-1.5 py-0.5 break-all"
              >
                {s}
              </span>
            ))}
          </div>
        )}

        {translation?.proof && translation.token && (
          <div className="mt-2.5">
            <button type="button" onClick={translateAnswer} disabled={translating}
              className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline disabled:opacity-60">
              {translating
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <Languages className="h-3.5 w-3.5" />}
              {translating
                ? 'Translating...'
                : targetLanguage === 'ur'
                  ? 'Translate to Urdu'
                  : 'Translate to English'}
            </button>
            {translationError && (
              <p role="alert" className="mt-1 text-xs text-danger">
                {translationError}
              </p>
            )}
          </div>
        )}

        {/* Always visible on touch devices (no hover); hover-reveal on desktop */}
        <div className="flex items-center gap-1 mt-2.5 pt-2.5 border-t border-border md:opacity-0 md:group-hover:opacity-100 transition-opacity">
          <MiniButton onClick={handleCopy} title="Copy response">
            {copied ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
          </MiniButton>
          <MiniButton onClick={handleExport} title="Export response">
            <Download className="w-3.5 h-3.5" />
          </MiniButton>
          {isLast && onRegenerate && (
            <MiniButton onClick={onRegenerate} title="Regenerate">
              <RotateCcw className="w-3.5 h-3.5" />
            </MiniButton>
          )}
          <span className="w-px h-3.5 bg-border mx-0.5" />
          <MiniButton onClick={() => setFeedback(feedback === 'up' ? null : 'up')} title="Good response">
            <ThumbsUp className={`w-3.5 h-3.5 ${feedback === 'up' ? 'text-primary' : ''}`} />
          </MiniButton>
          <MiniButton onClick={() => setFeedback(feedback === 'down' ? null : 'down')} title="Poor response">
            <ThumbsDown className={`w-3.5 h-3.5 ${feedback === 'down' ? 'text-danger' : ''}`} />
          </MiniButton>
        </div>
      </div>
      {time && <span className="text-[11px] text-ink-secondary/70 mt-1 ml-0.5">{time}</span>}
    </div>
  )
}

function MiniButton({ children, onClick, title }) {
  return (
    <button
      onClick={onClick}
      title={title}
      aria-label={title}
      className="w-7 h-7 sm:w-6 sm:h-6 rounded-md flex items-center justify-center text-ink-secondary hover:bg-slate-50 hover:text-ink transition-colors"
    >
      {children}
    </button>
  )
}
