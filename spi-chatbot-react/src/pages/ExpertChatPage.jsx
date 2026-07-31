import { useEffect, useRef, useState } from 'react'
import Breadcrumb from '../layout/Breadcrumb.jsx'
import ChatMessage from '../components/ChatMessage.jsx'
import TypingIndicator from '../components/TypingIndicator.jsx'
import MessageInput from '../components/MessageInput.jsx'
import SuggestionChip from '../components/SuggestionChip.jsx'

/**
 * Shared chat UI for any RAG-based expert (Implementation, Support, and
 * later Project Knowledge). Mirrors the backend architecture: one engine
 * (rag.py), reused per expert — this is the same idea on the frontend,
 * one component, reused per expert, differing only by which endpoint and
 * suggested prompts get passed in.
 *
 * Backend contract (unchanged, matches app.py exactly):
 *   POST {endpoint}  { question }  ->  { reply, sources }
 * No conversation memory here — each question is independent, since the
 * backend's RAG endpoints don't support interaction chaining like
 * /api/chat does for BI Expert.
 */
export default function ExpertChatPage({ title, description, breadcrumb, endpoint, suggestions }) {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  async function handleSend(text) {
    setMessages((prev) => [...prev, { role: 'user', content: text, timestamp: Date.now() }])
    setLoading(true)
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text }),
      })
      const data = await res.json()
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.reply, sources: data.sources, timestamp: Date.now() },
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
  }

  function handleRegenerate() {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user')
    if (lastUser) handleSend(lastUser.content)
  }

  const hasMessages = messages.length > 0

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-6 pt-4 pb-3 border-b border-border bg-surface">
        <Breadcrumb items={breadcrumb} />
        <h1 className="text-[17px] font-semibold text-ink">{title}</h1>
        <p className="text-[13px] text-ink-secondary mt-0.5">{description}</p>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6 flex flex-col gap-4">
          {!hasMessages && (
            <div className="flex flex-wrap gap-2 mb-2">
              {suggestions.map((s) => (
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
              sources={m.sources}
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
