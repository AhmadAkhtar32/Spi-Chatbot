import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import ChatMessage from './ChatMessage.jsx'
import TypingIndicator from './TypingIndicator.jsx'
import BackToWorkspaceButton from './BackToWorkspaceButton.jsx'

export default function ChatWindow({ messages, loading, onBack }) {
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
      className="flex-1 flex flex-col min-h-0"
    >
      <div className="px-6 pt-3.5 pb-2 border-b border-[#D1D5DB] bg-white">
        <BackToWorkspaceButton onClick={onBack} />
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6 flex flex-col gap-4">
          {messages.map((m, i) => (
            <ChatMessage
              key={i}
              role={m.role}
              content={m.content}
              trace={m.trace}
              timestamp={m.timestamp}
            />
          ))}
          {loading && <TypingIndicator />}
        </div>
      </div>
    </motion.div>
  )
}
