import { useEffect, useRef, useState } from 'react'
import { Send, Paperclip, Mic, X } from 'lucide-react'

const MAX_CHARS = 2000

export default function MessageInput({ onSend, disabled, value, onValueChange, onClear, hasMessages }) {
  const [internalValue, setInternalValue] = useState('')
  const textareaRef = useRef(null)

  // Supports being driven externally (e.g. a suggested prompt pre-filling
  // the box) while still working as an ordinary controlled input.
  const text = value !== undefined ? value : internalValue
  const setText = onValueChange !== undefined ? onValueChange : setInternalValue

  // Auto-expanding textarea — grows with content up to a max height.
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }, [text])

  function submit(e) {
    e?.preventDefault()
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
  }

  function handleKeyDown(e) {
    // Enter sends; Shift+Enter inserts a newline — standard chat convention.
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={submit} className="shrink-0 border-t border-border bg-surface px-6 py-3.5">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-end gap-2">
          <button
            type="button"
            disabled
            title="Attachments coming soon"
            className="h-10 w-10 shrink-0 rounded-md border border-border bg-bg
                       flex items-center justify-center text-ink-secondary/50 cursor-not-allowed mb-[3px]"
          >
            <Paperclip className="w-4 h-4" strokeWidth={2} />
          </button>

          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              rows={1}
              value={text}
              maxLength={MAX_CHARS}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about inventory, sales, finance, payroll or ERP navigation..."
              className="w-full resize-none px-4 py-2.5 rounded-md border border-border bg-bg text-[14px] text-ink
                         placeholder:text-ink-secondary/60 focus:outline-none focus:border-primary
                         focus:bg-surface transition-colors leading-relaxed"
              style={{ minHeight: '40px', maxHeight: '160px' }}
            />
          </div>

          <button
            type="button"
            disabled
            title="Voice input coming soon"
            className="h-10 w-10 shrink-0 rounded-md border border-border bg-bg
                       flex items-center justify-center text-ink-secondary/50 cursor-not-allowed mb-[3px]"
          >
            <Mic className="w-4 h-4" strokeWidth={2} />
          </button>

          <button
            type="submit"
            disabled={disabled || !text.trim()}
            className="h-10 w-10 shrink-0 rounded-md bg-primary flex items-center justify-center mb-[3px]
                       hover:bg-primary-dark transition-colors disabled:opacity-40 disabled:cursor-not-allowed
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            aria-label="Send message"
          >
            <Send className="w-4 h-4 text-white" strokeWidth={2} />
          </button>
        </div>

        <div className="flex items-center justify-between mt-1.5 px-1">
          <div className="flex items-center gap-3">
            <span className="text-[11px] text-ink-secondary/70">
              Enter to send &middot; Shift+Enter for new line
            </span>
            {hasMessages && onClear && (
              <button
                type="button"
                onClick={onClear}
                className="flex items-center gap-1 text-[11px] text-ink-secondary/70 hover:text-danger transition-colors"
              >
                <X className="w-3 h-3" />
                Clear conversation
              </button>
            )}
          </div>
          <span className="text-[11px] text-ink-secondary/50 tabular-nums">
            {text.length}/{MAX_CHARS}
          </span>
        </div>
      </div>
    </form>
  )
}
