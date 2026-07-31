import { useState } from 'react'
import { Copy, Check, Download, RotateCcw, ThumbsUp, ThumbsDown } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import StatusBadge from './StatusBadge.jsx'

// Recognized business states get rewritten into a marker the markdown
// renderer picks up and swaps for a StatusBadge, e.g. "Shipped" ->
// `STATUS:success:Shipped`. This keeps badge logic in one place instead
// of hand-parsing the reply in multiple components.
const STATUS_PATTERNS = [
  [/\bout of stock\b/gi, 'error', 'Out of Stock'],
  [/\bin stock\b/gi, 'success', 'In Stock'],
  [/\bshipped\b/gi, 'success', 'Shipped'],
  [/\bdelivered\b/gi, 'success', 'Delivered'],
  [/\bprocessing\b/gi, 'warning', 'Processing'],
  [/\bpending\b/gi, 'warning', 'Pending'],
]

function markStatuses(text) {
  let out = text
  for (const [pattern, type, label] of STATUS_PATTERNS) {
    out = out.replace(pattern, () => '`STATUS:' + type + ':' + label + '`')
  }
  return out
}

// Real fenced code blocks (```...```) come through with a `className`
// like "language-js"; a bare inline `code` span does not. That's how we
// tell an actual code block apart from our inline STATUS: marker.
function CodeRenderer({ className, children }) {
  const raw = String(children).replace(/\n$/, '')
  if (!className && raw.startsWith('STATUS:')) {
    const [, type, label] = raw.split(':')
    return <StatusBadge type={type} label={label} />
  }
  if (!className) return <code>{children}</code>
  return <code className={className}>{children}</code>
}

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function ChatMessage({ role, content, trace, sources, timestamp, onRegenerate, isLast }) {
  const [copied, setCopied] = useState(false)
  const [feedback, setFeedback] = useState(null) // 'up' | 'down' | null
  const isUser = role === 'user'
  const time = timestamp ? formatTime(new Date(timestamp)) : null

  function handleCopy() {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  function handleExport() {
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `spi-response-${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (isUser) {
    return (
      <div className="flex flex-col items-end animate-fade-in">
        <div className="max-w-[75%] bg-primary/8 border border-primary/15 rounded-lg px-4 py-2.5 text-[14px] text-ink">
          {content}
        </div>
        {time && <span className="text-[11px] text-ink-secondary/70 mt-1 mr-0.5">{time}</span>}
      </div>
    )
  }

  return (
    <div className="flex flex-col items-start animate-fade-in">
      <div className="max-w-[80%] group relative card px-4 py-3">
        {trace && trace.length > 0 && (
          <div className="text-[11px] font-mono text-ink-secondary/80 mb-2 pb-2 border-b border-border">
            {trace.join(', ')}
          </div>
        )}
        <div className="assistant-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeRenderer }}>
            {markStatuses(content)}
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
                className="text-[11px] font-mono text-ink-secondary bg-bg border border-border rounded px-1.5 py-0.5"
              >
                {s}
              </span>
            ))}
          </div>
        )}

        <div className="flex items-center gap-1 mt-2.5 pt-2.5 border-t border-border opacity-0 group-hover:opacity-100 transition-opacity">
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
      className="w-6 h-6 rounded-md flex items-center justify-center text-ink-secondary hover:bg-slate-50 hover:text-ink transition-colors"
    >
      {children}
    </button>
  )
}
