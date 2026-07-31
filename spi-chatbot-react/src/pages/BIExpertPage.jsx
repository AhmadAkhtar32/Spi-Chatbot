import { useEffect, useRef, useState } from 'react'
import { PackageSearch, ClipboardList, Compass, BarChart3 } from 'lucide-react'
import Breadcrumb from '../layout/Breadcrumb.jsx'
import ChatMessage from '../components/ChatMessage.jsx'
import TypingIndicator from '../components/TypingIndicator.jsx'
import MessageInput from '../components/MessageInput.jsx'
import SuggestionChip from '../components/SuggestionChip.jsx'

const SUGGESTIONS = [
  { icon: PackageSearch, label: 'Check stock availability', prompt: "What's the stock of Pepsi?" },
  { icon: ClipboardList, label: 'Order status', prompt: "What's the status of order #1234?" },
  { icon: Compass, label: 'Find Purchase Order screen', prompt: 'Where do I create a purchase order?' },
  { icon: BarChart3, label: 'Inventory report', prompt: 'Show me the inventory stock report' },
]

export default function BIExpertPage() {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [interactionId, setInteractionId] = useState(null)
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  // --- Backend integration — identical to the previous version. ---
  // Endpoint, request shape, and response shape are all unchanged:
  // POST /api/chat { message, interaction_id } -> { reply, trace, interaction_id }
  async function handleSend(text) {
    setMessages((prev) => [...prev, { role: 'user', content: text, timestamp: Date.now() }])
    setLoading(true)
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, interaction_id: interactionId }),
      })
      const data = await res.json()
      setInteractionId(data.interaction_id ?? null)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.reply, trace: data.trace, timestamp: Date.now() },
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
    setInteractionId(null)
  }

  function handleRegenerate() {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user')
    if (lastUser) handleSend(lastUser.content)
  }

  const hasMessages = messages.length > 0

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-6 pt-4 pb-3 border-b border-border bg-surface">
        <Breadcrumb items={['Dashboard', 'BI Expert']} />
        <h1 className="text-[17px] font-semibold text-ink">BI Expert</h1>
        <p className="text-[13px] text-ink-secondary mt-0.5">
          Ask about inventory, orders, and ERP navigation — answered from live SPI functions.
        </p>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6 flex flex-col gap-4">
          {!hasMessages && (
            <div className="flex flex-wrap gap-2 mb-2">
              {SUGGESTIONS.map((s) => (
                <SuggestionChip
                  key={s.label}
                  icon={s.icon}
                  label={s.label}
                  onClick={() => handleSend(s.prompt)}
                />
              ))}
            </div>
          )}

          {messages.map((m, i) => (
            <ChatMessage
              key={i}
              role={m.role}
              content={m.content}
              trace={m.trace}
              timestamp={m.timestamp}
              isLast={i === messages.length - 1 && m.role === 'assistant'}
              onRegenerate={handleRegenerate}
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
