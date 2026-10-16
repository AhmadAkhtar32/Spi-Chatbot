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

// Legacy preview only. Demo mode uses verified module licenses.
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

// Legacy preview only. Demo mode fetches its questions.
const LEGACY_SUGGESTIONS = [
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
    prompt:
      'Why does SPI slow down specifically during month-end close?',
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

export default function UnifiedChatPage({
  demoMode = false,
}) {
  const {
    conversationId,
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

  const [demoSuggestions, setDemoSuggestions] =
    useState([])

  const [suggestionsLoading, setSuggestionsLoading] =
    useState(false)

  const [suggestionsError, setSuggestionsError] =
    useState('')

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
      demoSession?.user.experts?.find(
        (name) => EXPERT_ROUTES[name]
      ) || ''
    )

    setSelectedModule(
      demoSession?.user.modules?.[0] || ''
    )

    setInputValue('')
  }, [demoMode, demoSession?.token])

  useEffect(() => {
    if (
      !demoMode ||
      !demoSession?.token ||
      !selectedExpert ||
      !selectedModule
    ) {
      return
    }

    const controller = new AbortController()

    setDemoSuggestions([])
    setSuggestionsError('')
    setSuggestionsLoading(true)

    const query = new URLSearchParams({
      expert: selectedExpert,
      module: selectedModule,
    })

    fetch(
      `${API_BASE}/api/demo/experts/suggestions?${query}`,
      {
        cache: 'no-store',
        signal: controller.signal,
        headers: {
          Authorization:
            `Bearer ${demoSession.token}`,
        },
      }
    )
      .then(async (response) => {
        if (response.status === 401) {
          switchDemoUser(
            'Demo session expired. Enter the presenter PIN again.'
          )
          return null
        }

        if (response.status === 403) {
          throw new Error(
            'Suggestions are not licensed for this expert or module.'
          )
        }

        if (!response.ok) {
          throw new Error(
            `Could not load suggestions (${response.status}).`
          )
        }

        return response.json()
      })
      .then((data) => {
        if (
          !controller.signal.aborted &&
          data
        ) {
          setDemoSuggestions(
            data.suggestions || []
          )
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setSuggestionsError(
            error.message ||
            'Could not load suggestions.'
          )
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setSuggestionsLoading(false)
        }
      })

    return () => controller.abort()
  }, [
    demoMode,
    demoSession?.token,
    selectedExpert,
    selectedModule,
    conversationId,
  ])

  const allowedExperts =
    demoSession?.user.experts?.filter(
      (name) => EXPERT_ROUTES[name]
    ) || []

  const allowedModules = demoMode
    ? demoSession?.user.modules || []
    : LICENSED_MODULES

  const suggestions = demoMode
    ? demoSuggestions.map((item, index) => ({
        icon: [
          FileText,
          BookOpen,
          BarChart3,
          Copy,
          RotateCcw,
          AlertCircle,
        ][index % 6],
        category:
          MODULE_LABELS[selectedModule] ||
          selectedModule,
        label: item.question,
        description: `From ${item.source}`,
        prompt: item.question,
        source: item.source,
      }))
    : LEGACY_SUGGESTIONS.filter((item) =>
        LICENSED_MODULES.includes(
          item.module
        )
      )

  const moduleLabel =
    MODULE_LABELS[selectedModule] ||
    selectedModule

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

  async function handleSend(
    text,
    source = null
  ) {
    if (
      !text?.trim() ||
      loading ||
      (
        demoMode &&
        (
          !demoSession ||
          !selectedExpert ||
          !selectedModule
        )
      )
    ) {
      return
    }

    const tokenAtSend =
      demoSession?.token

    const newUserMessage = {
      role: 'user',
      content: text,
      timestamp: Date.now(),
    }

    setMessages((previous) => [
      ...previous,
      newUserMessage,
    ])

    setLoading(true)

    try {
      const response = demoMode
        ? await fetch(
            `${API_BASE}/api/demo/experts/${
              EXPERT_ROUTES[selectedExpert]
            }`,
            {
              method: 'POST',
              cache: 'no-store',
              headers: {
                'Content-Type':
                  'application/json',
                Authorization:
                  `Bearer ${tokenAtSend}`,
              },
              body: JSON.stringify({
                question: text,
                module: selectedModule,
                source,
              }),
            }
          )
        : await fetch(
            `${API_BASE}/api/unified-chat`,
            {
              method: 'POST',
              headers: {
                'Content-Type':
                  'application/json',
              },
              body: JSON.stringify({
                message: text,
                history: messages
                  .slice(-8)
                  .map((message) => ({
                    role: message.role,
                    content:
                      message.content,
                  })),
              }),
            }
          )

      if (
        demoMode &&
        activeTokenRef.current !==
          tokenAtSend
      ) {
        return
      }

      if (
        demoMode &&
        response.status === 401
      ) {
        switchDemoUser(
          'Demo session expired. Enter the presenter PIN again.'
        )
        return
      }

      if (!response.ok) {
        if (
          demoMode &&
          response.status === 403
        ) {
          throw new Error(
            'This expert or module is not licensed for this user.'
          )
        }

        throw new Error(
          `Assistant request failed (${response.status}).`
        )
      }

      const data = await response.json()

      if (
        demoMode &&
        activeTokenRef.current !==
          tokenAtSend
      ) {
        return
      }

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content:
            data.reply ||
            'I received an empty response from the backend service.',
          sources: demoMode
            ? data.sources || []
            : undefined,
          timestamp: Date.now(),
        },
      ])
    } catch (error) {
      console.error(
        'Chat request failed:',
        error
      )

      if (
        demoMode &&
        activeTokenRef.current !==
          tokenAtSend
      ) {
        return
      }

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content: demoMode
            ? error.message ||
              'The demo expert is unavailable right now.'
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
    setSelectedExpert(
      event.target.value
    )

    resetDemoChats()
    setInputValue('')
  }

  function changeModule(event) {
    setSelectedModule(
      event.target.value
    )

    resetDemoChats()
    setInputValue('')
  }

  const hasMessages =
    messages.length > 0

  return (
    <div className="flex-1 relative overflow-hidden flex flex-col">
      <AnimatedBackground />

      {demoMode &&
        (
          allowedExperts.length > 1 ||
          allowedModules.length > 1
        ) && (
          <div className="relative z-10 shrink-0 border-b border-border bg-surface/90 px-5 py-2 flex flex-wrap gap-3 items-center text-xs">
            {allowedExperts.length > 1 && (
              <label>
                Expert{' '}

                <select
                  value={selectedExpert}
                  onChange={changeExpert}
                  className="ml-1 rounded-md border border-border bg-bg px-2 py-1"
                >
                  {allowedExperts.map(
                    (name) => (
                      <option
                        key={name}
                        value={name}
                      >
                        {name ===
                        'support_expert'
                          ? 'Support'
                          : 'Implementation'}
                      </option>
                    )
                  )}
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
                  {allowedModules.map(
                    (name) => (
                      <option
                        key={name}
                        value={name}
                      >
                        {MODULE_LABELS[name] ||
                          name}
                      </option>
                    )
                  )}
                </select>
              </label>
            )}
          </div>
        )}

      {!hasMessages ? (
        <div className="flex-1 min-h-0 overflow-y-auto flex flex-col items-center justify-center px-6 py-5 relative z-10">
          <motion.h1
            initial={{
              opacity: 0,
              y: 10,
            }}
            animate={{
              opacity: 1,
              y: 0,
            }}
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
              {suggestions.map(
                (suggestion) => (
                  <SuggestionChip
                    key={suggestion.label}
                    icon={suggestion.icon}
                    label={suggestion.label}
                    description={
                      suggestion.description
                    }
                    category={
                      suggestion.category
                    }
                    onClick={() =>
                      handleSend(
                        suggestion.prompt,
                        suggestion.source ||
                          null
                      )
                    }
                  />
                )
              )}
            </div>

            {demoMode &&
              suggestionsLoading && (
                <p
                  role="status"
                  className="mt-4 text-center text-xs text-ink-secondary"
                >
                  Finding questions in your approved reference material…
                </p>
              )}

            {demoMode &&
              suggestionsError && (
                <p
                  role="alert"
                  className="mt-4 text-center text-xs text-red-600"
                >
                  {suggestionsError}
                </p>
              )}

            {demoMode &&
              !suggestionsLoading &&
              !suggestionsError &&
              suggestions.length < 6 && (
                <p className="mt-4 text-center text-xs text-ink-secondary">
                  {suggestions.length} approved questions available for this expert and module.
                </p>
              )}
          </div>
        </div>
      ) : (
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto relative z-10"
        >
          <div className="max-w-3xl mx-auto px-6 py-6 flex flex-col gap-4">
            {messages.map(
              (message, index) => (
                <ChatMessage
                  key={index}
                  role={message.role}
                  content={
                    message.content
                  }
                  sources={
                    message.sources
                  }
                  timestamp={
                    message.timestamp
                  }
                />
              )
            )}

            {loading && (
              <TypingIndicator />
            )}
          </div>
        </div>
      )}

      <div className="relative z-10">
        <MessageInput
          onSend={handleSend}
          disabled={loading}
          value={inputValue}
          onValueChange={
            setInputValue
          }
          onClear={handleClear}
          hasMessages={
            hasMessages
          }
          inputPlaceholder={
            placeholder
          }
          voiceEnabled={
            !demoMode
          }
        />
      </div>
    </div>
  )
}