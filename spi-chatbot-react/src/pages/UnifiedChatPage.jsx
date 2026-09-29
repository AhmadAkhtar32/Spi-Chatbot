import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  FileText,
  BookOpen,
  BarChart3,
  Copy,
  RotateCcw,
  AlertCircle,
} from 'lucide-react'

import ChatMessage from '../components/ChatMessage.jsx'
import TypingIndicator from '../components/TypingIndicator.jsx'
import MessageInput from '../components/MessageInput.jsx'
import SuggestionChip from '../components/SuggestionChip.jsx'
import AnimatedBackground from '../components/AnimatedBackground.jsx'
import { API_BASE } from '../api.js'

function getGreeting() {
  const hour = new Date().getHours()

  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

// Modules this user is licensed for.
// Hardcoded to Financials for now.
const LICENSED_MODULES = ['financials']

const MODULE_LABELS = {
  financials: 'Financials',
  inventory: 'Inventory',
  payroll: 'Payroll',
}

// Suggestions available for each module.
const ALL_SUGGESTIONS = [
  {
    module: 'financials',
    icon: FileText,
    category: 'Vouchers',
    label: 'Set up a voucher type',
    description: 'Configure a GL voucher type for transactions.',
    prompt: 'How do I set up a GL voucher type?',
  },
  {
    module: 'financials',
    icon: BookOpen,
    category: 'Chart of Accounts',
    label: 'Manage account codes',
    description: 'Learn the account code length and structure.',
    prompt:
      'What is the maximum length of an account code in the Chart of Accounts?',
  },
  {
    module: 'financials',
    icon: Copy,
    category: 'Vouchers',
    label: 'Save default vouchers',
    description: 'Create reusable templates for repeated entries.',
    prompt:
      'How do I save a voucher as a default voucher for repeated entries?',
  },
  {
    module: 'financials',
    icon: RotateCcw,
    category: 'Reversals',
    label: 'Reverse a posted voucher',
    description: 'Correct a voucher that was posted by mistake.',
    prompt:
      'A voucher was posted by mistake — can it be reversed, and how?',
  },
  {
    module: 'financials',
    icon: BarChart3,
    category: 'Performance',
    label: 'Month-end slowness',
    description: 'Troubleshoot performance during month-end close.',
    prompt: 'Why does SPI slow down specifically during month-end close?',
  },
  {
    module: 'financials',
    icon: AlertCircle,
    category: 'Reports',
    label: 'Blank report results',
    description: 'Diagnose reports that return no visible data.',
    prompt:
      'Why would a report return blank results even though data clearly exists?',
  },
]

const licensedLabels = LICENSED_MODULES
  .map((module) => MODULE_LABELS[module])
  .filter(Boolean)

const SUGGESTIONS = ALL_SUGGESTIONS.filter((suggestion) =>
  LICENSED_MODULES.includes(suggestion.module)
)

const SUBTITLE = `Ask about setup, usage, and troubleshooting for ${licensedLabels.join(
  ', '
)}.`

const PLACEHOLDER = `Ask about ${licensedLabels.join(', ')}...`

export default function UnifiedChatPage() {
  const { messages, setMessages } = useOutletContext()

  const [loading, setLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')

  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, loading])

  async function handleSend(text) {
    if (!text?.trim() || loading) return

    const newUserMessage = {
      role: 'user',
      content: text,
      timestamp: Date.now(),
    }

    setMessages((prev) => [...prev, newUserMessage])
    setLoading(true)

    try {
      // Send recent conversation history to the backend.
      const history = messages
        .slice(-8)
        .map((message) => ({
          role: message.role,
          content: message.content,
        }))

      const res = await fetch(`${API_BASE}/api/unified-chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: text,
          history,
        }),
      })

      if (!res.ok) {
        throw new Error(`Backend returned ${res.status}`)
      }

      const data = await res.json()

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            data.reply ||
            'I received an empty response from the backend service.',
          timestamp: Date.now(),
        },
      ])
    } catch (err) {
      console.error('Chat request failed:', err)

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            'Unable to reach the backend service. Confirm the API server is running.',
          timestamp: Date.now(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  function handleClear() {
    setMessages([])
    setInputValue('')
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
            transition={{
              duration: 0.5,
              ease: 'easeOut',
            }}
            className="
              text-[28px]
              font-bold
              mb-2
              tracking-tight
              text-center
              bg-gradient-to-r
              from-[#1E3A8A]
              via-primary
              to-[#1E3A8A]
              bg-[length:200%_auto]
              bg-clip-text
              text-transparent
              animate-shimmer
            "
          >
            {getGreeting()}
          </motion.h1>

          <p
            className="
              text-[13.5px]
              text-ink-secondary
              mb-7
              text-center
              max-w-md
              leading-relaxed
            "
          >
            {SUBTITLE}
          </p>

          <div className="w-full max-w-4xl mt-2">
  <div className="mb-3 flex items-center justify-between px-1">
    <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
      Quick actions
    </div>

    <div className="text-[11px] text-slate-400">
      Select a topic to get started
    </div>
  </div>

  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
    {SUGGESTIONS.map((suggestion) => (
      <SuggestionChip
        key={suggestion.label}
        icon={suggestion.icon}
        label={suggestion.label}
        description={suggestion.description}
        category={suggestion.category}
        onClick={() => handleSend(suggestion.prompt)}
      />
    ))}
  </div>
</div>
        </div>
      ) : (
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto relative z-10"
        >
          <div className="max-w-3xl mx-auto px-6 py-6 flex flex-col gap-4">
            {messages.map((message, index) => (
              <ChatMessage
                key={index}
                role={message.role}
                content={message.content}
                timestamp={message.timestamp}
              />
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
          inputPlaceholder={PLACEHOLDER}
        />
      </div>
    </div>
  )
}