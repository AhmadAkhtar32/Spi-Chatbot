import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { motion } from 'framer-motion'
import { PackageSearch, ClipboardList, Compass, LifeBuoy } from 'lucide-react'
import ChatMessage from '../components/ChatMessage.jsx'
import TypingIndicator from '../components/TypingIndicator.jsx'
import MessageInput from '../components/MessageInput.jsx'
import SuggestionChip from '../components/SuggestionChip.jsx'
import AnimatedBackground from '../components/AnimatedBackground.jsx'

function getGreeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

const SUGGESTIONS = [
  { icon: PackageSearch, label: 'Check stock availability', prompt: "What's the stock of Pepsi?" },
  { icon: ClipboardList, label: 'Order status', prompt: "What's the status of order #1234?" },
  { icon: Compass, label: 'Find a screen', prompt: 'Where do I create a purchase order?' },
  { icon: LifeBuoy, label: 'Troubleshoot an issue', prompt: 'Why would a user get logged out randomly?' },
]

export default function UnifiedChatPage() {
  const { messages, setMessages } = useOutletContext()
  const [loading, setLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  async function handleSend(text) {
    const newUserMessage = { role: 'user', content: text, timestamp: Date.now() }
    setMessages((prev) => [...prev, newUserMessage])
    setLoading(true)
    try {
      // Send recent history as plain {role, content} pairs — the backend
      // uses this for context on every category, since a single Gemini
      // interaction thread doesn't cleanly fit a conversation that can
      // jump between different internal experts turn to turn.
      const history = messages.slice(-8).map((m) => ({ role: m.role, content: m.content }))

      const res = await fetch('/api/unified-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history }),
      })
      const data = await res.json()
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply, timestamp: Date.now() }])
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

  const hasMessages = messages.length > 0

  return (
    <div className="flex-1 relative overflow-hidden flex flex-col">
      <AnimatedBackground />

      {!hasMessages ? (
        <div className="flex-1 flex flex-col items-center justify-center px-6 relative z-10">
          <motion.h1
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
            className="text-[28px] font-bold mb-2 tracking-tight text-center bg-gradient-to-r from-[#1E3A8A] via-primary to-[#1E3A8A]
                       bg-[length:200%_auto] bg-clip-text text-transparent animate-shimmer"
          >
            {getGreeting()}, Minahil
          </motion.h1>
          <p className="text-[13.5px] text-ink-secondary mb-7 text-center max-w-md leading-relaxed">
            Ask anything about inventory, orders, ERP navigation, setup, or troubleshooting.
          </p>
          <div className="flex flex-wrap justify-center gap-2 max-w-lg">
            {SUGGESTIONS.map((s) => (
              <SuggestionChip
                key={s.label}
                icon={s.icon}
                label={s.label}
                onClick={() => handleSend(s.prompt)}
              />
            ))}
          </div>
        </div>
      ) : (
        <div ref={scrollRef} className="flex-1 overflow-y-auto relative z-10">
          <div className="max-w-3xl mx-auto px-6 py-6 flex flex-col gap-4">
            {messages.map((m, i) => (
              <ChatMessage key={i} role={m.role} content={m.content} timestamp={m.timestamp} />
            ))}
            {loading && <TypingIndicator />}
          </div>
        </div>
      )}

      <div className="relative z-10">
        <MessageInput
          onSend={handleSend}
          disabled={loading}
          value={inputValue}
          onValueChange={setInputValue}
          onClear={handleClear}
          hasMessages={hasMessages}
        />
      </div>
    </div>
  )
}
