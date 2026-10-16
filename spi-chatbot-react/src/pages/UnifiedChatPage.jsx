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

const LICENSED_MODULES = ['financials']

const MODULE_LABELS = {
  financials: 'Financials',
  financial: 'Financials',
  inventory: 'Inventory',
  payroll: 'Payroll',
}

const EXPERT_ROUTES = {
  support_expert: 'support',
  implementation_expert: 'implementation',
}

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

// Demo suggestions match documents available to each expert and module.
// The backend still decides what each user is allowed to access.
const DEMO_SUGGESTIONS = [
  {
    expert: 'support_expert',
    module: 'financial',
    icon: FileText,
    category: 'Vouchers',
    label: 'Posting and verification',
    description: 'Understand when a voucher becomes locked.',
    prompt:
      'What happens when a GL voucher is posted, and how is that different from verification?',
  },
  {
    expert: 'support_expert',
    module: 'financial',
    icon: BookOpen,
    category: 'Voucher entry',
    label: 'Checks before saving',
    description: 'Review the balance and voucher date rules.',
    prompt: 'What must be checked before saving a GL voucher?',
  },
  {
    expert: 'support_expert',
    module: 'financial',
    icon: AlertCircle,
    category: 'Voucher entry',
    label: 'Period date rules',
    description: 'Check which voucher dates are accepted.',
    prompt: 'Which dates are allowed for a GL voucher in the current period?',
  },
  {
    expert: 'support_expert',
    module: 'inventory',
    icon: BarChart3,
    category: 'Stock support',
    label: 'Different stock counts',
    description: 'Troubleshoot a pending warehouse transfer.',
    prompt:
      'Why does the same item show different stock on the Stock Status Report versus the Warehouse Transfer screen?',
  },
  {
    expert: 'support_expert',
    module: 'inventory',
    icon: FileText,
    category: 'Stock support',
    label: 'Missing reorder suggestion',
    description: 'Check the preferred supplier configuration.',
    prompt:
      'Stock is below the reorder point, but no suggested Purchase Order appears. What should I check?',
  },
  {
    expert: 'support_expert',
    module: 'inventory',
    icon: AlertCircle,
    category: 'Stock support',
    label: 'Barcode not recognized',
    description: 'Diagnose a stock count scan.',
    prompt:
      'A barcode scan during a stock count says Item Not Found. What is a likely cause?',
  },
  {
    expert: 'implementation_expert',
    module: 'financial',
    icon: FileText,
    category: 'GL setup',
    label: 'Create voucher types',
    description: 'Configure a new GL voucher type.',
    prompt: 'How do I create a new GL voucher type?',
  },
  {
    expert: 'implementation_expert',
    module: 'financial',
    icon: BookOpen,
    category: 'GL setup',
    label: 'Add account codes',
    description: 'Set up the Chart of Accounts.',
    prompt: 'How do I add an account code in the Chart of Accounts?',
  },
  {
    expert: 'implementation_expert',
    module: 'financial',
    icon: Copy,
    category: 'Vouchers',
    label: 'Save default vouchers',
    description: 'Create a reusable voucher template.',
    prompt:
      'How do I save a voucher as a default voucher for repeated entries?',
  },
  {
    expert: 'implementation_expert',
    module: 'inventory',
    icon: BookOpen,
    category: 'Inventory setup',
    label: 'Setup prerequisites',
    description: 'Confirm what the client must provide first.',
    prompt:
      'What must be finalized before Inventory module configuration can begin?',
  },
  {
    expert: 'implementation_expert',
    module: 'inventory',
    icon: FileText,
    category: 'Inventory setup',
    label: 'Bin location codes',
    description: 'Use the format required by barcode scanning.',
    prompt: 'What format must Bin Location codes follow?',
  },
  {
    expert: 'implementation_expert',
    module: 'inventory',
    icon: BarChart3,
    category: 'Go-live',
    label: 'Inventory checklist',
    description: 'Review the documented go-live checks.',
    prompt: 'What should be checked on the Inventory go-live checklist?',
  },
]

export default function UnifiedChatPage({ demoMode = false }) {
  const {
    messages,
    setMessages,
    demoSession,
    switchDemoUser,
    resetDemoChats,
  } = useOutletContext()

  const [loading, setLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [selectedExpert, setSelectedExpert] = useState('')
  const [selectedModule, setSelectedModule] = useState('')

  const scrollRef = useRef(null)
  const activeTokenRef = useRef(demoSession?.token)

  activeTokenRef.current = demoSession?.token

  useEffect(() => {
    activeTokenRef.current = demoSession?.token

    return () => {
      activeTokenRef.current = null
    }
  }, [demoSession?.token])

  useEffect(() => {
    if (!demoMode) return

    setSelectedExpert(
      demoSession?.user.experts?.find((name) => EXPERT_ROUTES[name]) || ''
    )
    setSelectedModule(demoSession?.user.modules?.[0] || '')
    setInputValue('')
  }, [demoMode, demoSession?.token])

  const allowedExperts =
    demoSession?.user.experts?.filter((name) => EXPERT_ROUTES[name]) || []

  const allowedModules = demoMode
    ? demoSession?.user.modules || []
    : LICENSED_MODULES

  const suggestions = demoMode
    ? DEMO_SUGGESTIONS.filter(
        (item) =>
          item.expert === selectedExpert &&
          item.module === selectedModule
      )
    : ALL_SUGGESTIONS.filter((item) =>
        LICENSED_MODULES.includes(item.module)
      )

  const moduleLabel = MODULE_LABELS[selectedModule] || selectedModule

  const subtitle = demoMode
    ? `Ask the ${
        selectedExpert === 'support_expert'
          ? 'Support'
          : 'Implementation'
      } Expert about ${moduleLabel}. Answers use approved demo documents.`
    : 'Ask about setup, usage, and troubleshooting for Financials.'

  const placeholder = demoMode
    ? `Ask about ${moduleLabel}...`
    : 'Ask about Financials...'

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, loading])

  async function handleSend(text) {
    if (
      !text?.trim() ||
      loading ||
      (demoMode &&
        (!demoSession || !selectedExpert || !selectedModule))
    ) {
      return
    }

    const tokenAtSend = demoSession?.token

    const newUserMessage = {
      role: 'user',
      content: text,
      timestamp: Date.now(),
    }

    setMessages((prev) => [...prev, newUserMessage])
    setLoading(true)

    try {
      const res = demoMode
        ? await fetch(
            `${API_BASE}/api/demo/experts/${EXPERT_ROUTES[selectedExpert]}`,
            {
              method: 'POST',
              cache: 'no-store',
              headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${tokenAtSend}`,
              },
              body: JSON.stringify({
                question: text,
                module: selectedModule,
              }),
            }
          )
        : await fetch(`${API_BASE}/api/unified-chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              message: text,
              history: messages.slice(-8).map((message) => ({
                role: message.role,
                content: message.content,
              })),
            }),
          })

      if (demoMode && activeTokenRef.current !== tokenAtSend) {
        return
      }

      if (demoMode && res.status === 401) {
        switchDemoUser(
          'Demo session expired. Enter the presenter PIN again.'
        )
        return
      }

      if (!res.ok) {
        if (demoMode && res.status === 403) {
          throw new Error(
            'This expert or module is not licensed for this user.'
          )
        }

        throw new Error(`Assistant request failed (${res.status}).`)
      }

      const data = await res.json()

      if (demoMode && activeTokenRef.current !== tokenAtSend) {
        return
      }

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            data.reply ||
            'I received an empty response from the backend service.',
          sources: demoMode ? data.sources || [] : undefined,
          timestamp: Date.now(),
        },
      ])
    } catch (err) {
      console.error('Chat request failed:', err)

      if (demoMode && activeTokenRef.current !== tokenAtSend) {
        return
      }

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: demoMode
            ? err.message || 'The demo expert is unavailable right now.'
            : 'Unable to reach the backend service. Confirm the API server is running.',
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

  function changeExpert(event) {
    setSelectedExpert(event.target.value)
    resetDemoChats()
    setInputValue('')
  }

  function changeModule(event) {
    setSelectedModule(event.target.value)
    resetDemoChats()
    setInputValue('')
  }

  const hasMessages = messages.length > 0

  return (
    <div className="flex-1 relative overflow-hidden flex flex-col">
      <AnimatedBackground />

      {demoMode &&
        (allowedExperts.length > 1 ||
          allowedModules.length > 1) && (
          <div className="relative z-10 shrink-0 border-b border-border bg-surface/90 px-5 py-2 flex flex-wrap gap-3 items-center text-xs">
            {allowedExperts.length > 1 && (
              <label>
                Expert{' '}

                <select
                  value={selectedExpert}
                  onChange={changeExpert}
                  className="ml-1 rounded-md border border-border bg-bg px-2 py-1"
                >
                  {allowedExperts.map((name) => (
                    <option key={name} value={name}>
                      {name === 'support_expert'
                        ? 'Support'
                        : 'Implementation'}
                    </option>
                  ))}
                </select>
              </label>
            )}

            {allowedModules.length > 1 && (
              <label>
                Module{' '}

                <select
                  value={selectedModule}
                  onChange={changeModule}
                  className="ml-1 rounded-md border border-border bg-bg px-2 py-1"
                >
                  {allowedModules.map((name) => (
                    <option key={name} value={name}>
                      {MODULE_LABELS[name] || name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
        )}

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
            {subtitle}
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
              {suggestions.map((suggestion) => (
                <SuggestionChip
                  key={`${suggestion.module}-${suggestion.label}`}
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
                sources={message.sources}
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
          inputPlaceholder={placeholder}
          voiceEnabled={!demoMode}
        />
      </div>
    </div>
  )
}