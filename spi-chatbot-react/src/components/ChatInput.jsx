import { useState } from 'react'
import { Send } from 'lucide-react'

export default function ChatInput({ onSend, disabled }) {
  const [value, setValue] = useState('')

  function submit(e) {
    e.preventDefault()
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  return (
    <form
      onSubmit={submit}
      className="shrink-0 border-t border-border bg-surface px-6 py-4"
    >
      <div className="max-w-3xl mx-auto flex items-center gap-3">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Ask about inventory, orders, reports, or ERP navigation..."
          className="flex-1 h-11 px-4 rounded-md border border-border bg-bg text-[14px] text-ink
                     placeholder:text-ink-secondary/70 focus:outline-none focus:border-primary
                     focus:bg-surface transition-colors"
        />
        <button
          type="submit"
          disabled={disabled}
          className="h-11 w-11 shrink-0 rounded-md bg-primary flex items-center justify-center
                     hover:bg-primary-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed
                     focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          aria-label="Send message"
        >
          <Send className="w-4 h-4 text-white" strokeWidth={2} />
        </button>
      </div>
    </form>
  )
}
