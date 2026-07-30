import { useEffect, useState } from 'react'
import { Send, Paperclip } from 'lucide-react'

export default function MessageInput({ onSend, disabled, value, onValueChange }) {
  const [internalValue, setInternalValue] = useState('')

  // Supports being driven externally (e.g. a Popular Task pre-filling
  // the box) while still working as an ordinary controlled input.
  const text = value !== undefined ? value : internalValue
  const setText = onValueChange !== undefined ? onValueChange : setInternalValue

  function submit(e) {
    e.preventDefault()
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
  }

  return (
    <form onSubmit={submit} className="shrink-0 border-t border-[#D1D5DB] bg-white px-6 py-4">
      <div className="max-w-3xl mx-auto flex items-center gap-2">
        <button
          type="button"
          disabled
          title="Attachments coming soon"
          className="h-11 w-11 shrink-0 rounded-md border border-[#D1D5DB] bg-[#F4F6F8]
                     flex items-center justify-center text-[#9CA3AF] cursor-not-allowed"
        >
          <Paperclip className="w-4 h-4" strokeWidth={2} />
        </button>

        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask about inventory, sales, finance, payroll or ERP navigation..."
          className="flex-1 h-11 px-4 rounded-md border border-[#D1D5DB] bg-[#F4F6F8] text-[14px] text-[#111827]
                     placeholder:text-[#9CA3AF] focus:outline-none focus:border-[#2563EB]
                     focus:bg-white transition-colors"
        />

        <button
          type="submit"
          disabled={disabled}
          className="h-11 w-11 shrink-0 rounded-md bg-[#2563EB] flex items-center justify-center
                     hover:bg-[#1D4ED8] transition-colors disabled:opacity-50 disabled:cursor-not-allowed
                     focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]/40"
          aria-label="Send message"
        >
          <Send className="w-4 h-4 text-white" strokeWidth={2} />
        </button>
      </div>
    </form>
  )
}
