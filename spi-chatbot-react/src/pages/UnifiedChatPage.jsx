import { useEffect, useLayoutEffect, useRef, useState } from 'react'
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
import { API_BASE } from '../api/client.js'

function getGreeting() {
  const hour = new Date().getHours()

  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

// Legacy preview only. Sample mode uses verified module licenses.
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

// Legacy preview only. Sample mode fetches its questions.
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
  licensedMode = false,
}) {
  const {
    conversationId,
    messages,
    setMessages,
    assistantSession,
    switchAssistantUser,
    resetAssistantChats,
    scrollHeaders,
    setScrollHeaders,
  } = useOutletContext()

  const [loading, setLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [selectedExpert, setSelectedExpert] = useState('')
  const [selectedModule, setSelectedModule] = useState('')

  const [expertSuggestions, setExpertSuggestions] =
    useState([])

  const [suggestionsLoading, setSuggestionsLoading] =
    useState(false)

  const [suggestionsError, setSuggestionsError] =
    useState('')

  const identityHeaderRef = useRef(null)
  const tabsHeaderRef = useRef(null)
  const scrollRef = useRef(null)
  const imageRequest = useRef(null)
  useEffect(() => () => imageRequest.current?.abort(), [conversationId, selectedExpert, selectedModule, assistantSession?.token])
  const activeTokenRef = useRef(assistantSession?.token)

  activeTokenRef.current = assistantSession?.token

  useEffect(() => {
    activeTokenRef.current = assistantSession?.token

    return () => {
      activeTokenRef.current = null
    }
  }, [assistantSession?.token])

  useEffect(() => {
    if (!licensedMode) return

    setSelectedExpert(
      assistantSession?.user.experts?.find(
        (name) => EXPERT_ROUTES[name]
      ) || ''
    )

    setSelectedModule(
      assistantSession?.user.modules?.[0] || ''
    )

    setInputValue('')
  }, [licensedMode, assistantSession?.token])

  useEffect(() => {
    if (
      !licensedMode ||
      !assistantSession?.token ||
      !selectedExpert ||
      !selectedModule
    ) {
      return
    }

    const controller = new AbortController()

    setExpertSuggestions([])
    setSuggestionsError('')
    setSuggestionsLoading(true)

    const query = new URLSearchParams({
      expert: selectedExpert,
      module: selectedModule,
    })

    fetch(
      `${API_BASE}/api/v1/experts/suggestions?${query}`,
      {
        cache: 'no-store',
        signal: controller.signal,
        headers: {
          Authorization:
            `Bearer ${assistantSession.token}`,
        },
      }
    )
      .then(async (response) => {
        if (response.status === 401) {
          switchAssistantUser(
            'Sample session expired. Enter the presenter PIN again.'
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
          setExpertSuggestions(
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
    licensedMode,
    assistantSession?.token,
    selectedExpert,
    selectedModule,
    conversationId,
  ])

  const allowedExperts =
    assistantSession?.user.experts?.filter(
      (name) => EXPERT_ROUTES[name]
    ) || []

  const allowedModules = licensedMode
    ? assistantSession?.user.modules || []
    : LICENSED_MODULES

  const suggestions = licensedMode
    ? expertSuggestions.map((item, index) => ({
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

  const subtitle = licensedMode
    ? `Ask the ${
        selectedExpert === 'support_expert'
          ? 'Support'
          : 'Implementation'
      } Expert about ${moduleLabel}. Answers use approved sample documents.`
    : 'Ask about setup, usage, and troubleshooting for Financials.'

  const placeholder = licensedMode
    ? `Ask about ${moduleLabel}...`
    : 'Ask about Financials...'

  useLayoutEffect(() => {
    if (!licensedMode || !setScrollHeaders) return

    setScrollHeaders({
      identity: identityHeaderRef.current,
      tabs: tabsHeaderRef.current,
    })

    return () => setScrollHeaders(null)
  }, [licensedMode, setScrollHeaders, messages.length === 0])

  // Read new replies from their beginning, not their final paragraph.
  useLayoutEffect(() => {
    const viewport = scrollRef.current
    if (!viewport) return

    if (!messages.length) {
      viewport.scrollTop = 0
      return
    }

    function alignLatest() {
      const rows = viewport.querySelectorAll('[data-chat-message]')
      const latest = rows[rows.length - 1]
      if (!latest) return

      const previous = rows[rows.length - 2]
      const isReply = latest.dataset.chatRole === 'assistant'
      const showQuestion = isReply &&
        previous?.dataset.chatRole === 'user' &&
        latest.offsetTop - previous.offsetTop <= viewport.clientHeight * 0.35

      const target = showQuestion ? previous : latest
      viewport.scrollTop = Math.max(0, target.offsetTop - 12)
    }

    alignLatest()
    const frame = requestAnimationFrame(alignLatest)
    return () => cancelAnimationFrame(frame)
  }, [messages, conversationId, scrollHeaders])

  async function handleSend(text, source = null, image = null) {
    if (
      !text?.trim() ||
      loading ||
      (
        licensedMode &&
        (
          !assistantSession ||
          !selectedExpert ||
          !selectedModule
        )
      )
    ) {
      return false
    }

    if (image && !licensedMode) return false
    const imageController = image ? new AbortController() : null
    if (imageController) imageRequest.current = imageController
    const imageTimeout = imageController ? setTimeout(() => imageController.abort(), 95000) : null

    const tokenAtSend =
      assistantSession?.token

    const newUserMessage = {
      role: 'user',
      content: text,
      attachment: image || undefined,
      timestamp: Date.now(),
    }

    setMessages((previous) => [
      ...previous,
      newUserMessage,
    ])

    setLoading(true)

    try {
      const response = image
        ? await fetch(`${API_BASE}/api/v1/experts/image-question?${new URLSearchParams({ expert: selectedExpert, module: selectedModule })}`, {
            method: 'POST', cache: 'no-store', signal: imageController.signal,
            headers: { Authorization: `Bearer ${tokenAtSend}`, 'Content-Type': image.type, 'X-SPIA-Question': btoa(String.fromCharCode(...new TextEncoder().encode(text))) }, body: image,
          })
        : licensedMode
        ? await fetch(
            `${API_BASE}/api/v1/experts/${
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

      if (imageController?.signal.aborted) return false
      if (
        licensedMode &&
        activeTokenRef.current !==
          tokenAtSend
      ) {
        return
      }

      if (imageController?.signal.aborted) return false
      if (
        licensedMode &&
        response.status === 401
      ) {
        switchAssistantUser(
          'Sample session expired. Enter the presenter PIN again.'
        )
        return
      }

      if (image && !response.ok && response.status !== 401) {
        const failure = await response.json().catch(() => ({}))
        throw new Error(typeof failure.detail === 'string' ? failure.detail : `Screenshot request failed (${response.status}).`)
      }
      if (!response.ok) {
        if (
          licensedMode &&
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

      if (imageController?.signal.aborted) return false
      if (
        licensedMode &&
        activeTokenRef.current !==
          tokenAtSend
      ) {
        return
      }

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          language: data.language,
          translation_proof: data.translation_proof,
          expert: EXPERT_ROUTES[selectedExpert],
          module: selectedModule,
          content:
            data.reply ||
            'I received an empty response from the backend service.',
          sources: licensedMode
            ? data.sources || []
            : undefined,
          timestamp: Date.now(),
        },
      ])
      return true
    } catch (error) {
      if (imageController?.signal.aborted) return false
      console.error(
        'Chat request failed:',
        error
      )

      if (imageController?.signal.aborted) return false
      if (
        licensedMode &&
        activeTokenRef.current !==
          tokenAtSend
      ) {
        return
      }

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content: licensedMode
            ? error.message ||
              'The sample expert is unavailable right now.'
            : 'Unable to reach the backend service. Confirm the API server is running.',
          timestamp: Date.now(),
        },
      ])
      return false
    } finally {
      clearTimeout(imageTimeout)
      if (imageRequest.current === imageController) imageRequest.current = null
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

    resetAssistantChats()
    setInputValue('')
  }

  function changeModule(event) {
    setSelectedModule(
      event.target.value
    )

    resetAssistantChats()
    setInputValue('')
  }

  const hasMessages =
    messages.length > 0

  return (
    <div className="flex-1 min-h-0 min-w-0 relative overflow-hidden flex flex-col">
      <AnimatedBackground />

      {licensedMode &&
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
        <div
          ref={scrollRef}
          role="region"
          aria-label="Suggested questions"
          tabIndex={0}
          className="flex-1 min-h-0 overflow-y-auto overscroll-contain relative z-10"
          style={{ overflowAnchor: 'none', scrollBehavior: 'auto' }}
        >
          <div ref={identityHeaderRef} />
          <div ref={tabsHeaderRef} />
          <div className="w-full flex flex-col items-center px-4 py-5 sm:px-6">
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
              mb-4
              text-center
              max-w-2xl
              leading-relaxed
            "
          >
            {subtitle}
          </p>

          <div className="w-full max-w-4xl">
            <div className="mb-2 flex items-center justify-between gap-2 px-1">
              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                Quick actions
              </div>

              <div className="text-[11px] text-slate-400">
                Select a topic to get started
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3 [&_button]:px-3 [&_button]:py-3">
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

            {licensedMode &&
              suggestionsLoading && (
                <p
                  role="status"
                  className="mt-4 text-center text-xs text-ink-secondary"
                >
                  Finding questions in your approved reference material…
                </p>
              )}

            {licensedMode &&
              suggestionsError && (
                <p
                  role="alert"
                  className="mt-4 text-center text-xs text-red-600"
                >
                  {suggestionsError}
                </p>
              )}

            {licensedMode &&
              !suggestionsLoading &&
              !suggestionsError &&
              suggestions.length < 6 && (
                <p className="mt-4 text-center text-xs text-ink-secondary">
                  {suggestions.length} approved questions available for this expert and module.
                </p>
              )}
          </div>
          </div>
        </div>
      ) : (
        <div
          ref={scrollRef}
          role="region"
          aria-label="Conversation"
          tabIndex={0}
          className="flex-1 min-h-0 overflow-y-auto overscroll-contain relative z-10"
          style={{ overflowAnchor: 'none', scrollBehavior: 'auto' }}
        >
          <div ref={identityHeaderRef} />
          <div ref={tabsHeaderRef} />
          <div className="max-w-3xl mx-auto px-6 py-6 flex flex-col gap-4">
            {messages.map(
              (message, index) => (
                <div key={index} data-chat-message data-chat-role={message.role}>
                <ChatMessage attachment={message.attachment}
                  role={message.role}
                  language={message.language}
                  translation={licensedMode && message.translation_proof ? {
                    token: assistantSession?.token,
                    proof: message.translation_proof,
                    expert: message.expert,
                    module: message.module,
                    sources: message.sources || [],
                    onSessionExpired: switchAssistantUser,
                  } : null}
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
                </div>
              )
            )}

            {loading && (
              <TypingIndicator />
            )}
          </div>
        </div>
      )}

      <div className="relative z-10 shrink-0">
        <MessageInput
          key={`${conversationId}:${selectedExpert}:${selectedModule}:${assistantSession?.token || ""}`}
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
          voiceEnabled={licensedMode && Boolean(assistantSession?.token && selectedExpert && selectedModule)}
          showVoiceControl={licensedMode}
          voiceContext={{ token: assistantSession?.token, expert: selectedExpert, module: selectedModule }}
          onVoiceSessionExpired={switchAssistantUser}
          imageEnabled={licensedMode && Boolean(assistantSession?.token && EXPERT_ROUTES[selectedExpert] && selectedModule)}
          showAttachments={false}
          maxChars={licensedMode ? 1000 : 2000}
        />
      </div>
    </div>
  )
}
