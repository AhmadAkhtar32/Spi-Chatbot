import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
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

export default function ChatMessage({ role, content, trace, timestamp }) {
  const [copied, setCopied] = useState(false)
  const isUser = role === 'user'
  const time = timestamp ? formatTime(new Date(timestamp)) : null

  function handleCopy() {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  if (isUser) {
    return (
      <div className="flex flex-col items-end animate-fade-in">
        <div className="max-w-[75%] bg-blue-50 border border-blue-100 rounded-lg px-4 py-2.5 text-[14px] text-[#111827]">
          {content}
        </div>
        {time && <span className="text-[11px] text-[#9CA3AF] mt-1 mr-0.5">{time}</span>}
      </div>
    )
  }

  return (
    <div className="flex flex-col items-start animate-fade-in">
      <div className="max-w-[80%] group relative bg-white border border-[#D1D5DB] rounded-lg px-4 py-3">
        {trace && trace.length > 0 && (
          <div className="text-[11px] font-mono text-[#6B7280]/80 mb-2 pb-2 border-b border-[#D1D5DB]">
            {trace.join(', ')}
          </div>
        )}
        <div className="assistant-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeRenderer }}>
            {markStatuses(content)}
          </ReactMarkdown>
        </div>

        <button
          onClick={handleCopy}
          className="absolute -bottom-3 -right-2 opacity-0 group-hover:opacity-100 transition-opacity
                     w-6 h-6 rounded-md bg-white border border-[#D1D5DB] flex items-center justify-center
                     hover:bg-slate-50"
          aria-label="Copy response"
        >
          {copied ? (
            <Check className="w-3 h-3 text-[#16A34A]" strokeWidth={2} />
          ) : (
            <Copy className="w-3 h-3 text-[#6B7280]" strokeWidth={2} />
          )}
        </button>
      </div>
      {time && <span className="text-[11px] text-[#9CA3AF] mt-1 ml-0.5">{time}</span>}
    </div>
  )
}
