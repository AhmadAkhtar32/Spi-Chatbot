import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Package,
  ShoppingCart,
  Truck,
  FileText,
  Wallet,
  LifeBuoy,
  RotateCw,
} from 'lucide-react'

import AnimatedBackground from '../components/AnimatedBackground.jsx'
import ChatMessage from '../components/ChatMessage.jsx'
import MessageInput from '../components/MessageInput.jsx'
import SuggestionChip from '../components/SuggestionChip.jsx'
import TypingIndicator from '../components/TypingIndicator.jsx'
import { API_BASE } from '../api/client.js'
import {
  planBusinessQuestion,
  pagePath,
  isRecordPath,
  businessAnswer,
} from '../services/businessQuestions.js'

const KINDS = {
  stock: { label: 'Inventory', icon: Package },
  sales_orders: { label: 'Sales', icon: ShoppingCart },
  purchase_orders: { label: 'Purchasing', icon: Truck },
  credit_return_notes: { label: 'Returns', icon: FileText },
  payroll: { label: 'Payroll', icon: Wallet },
  tickets: { label: 'Support', icon: LifeBuoy },
}

function greeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

export default function BusinessPage() {
  const {
    conversationId,
    messages,
    setMessages,
    assistantSession,
    switchAssistantUser,
  } = useOutletContext()

  const [input, setInput] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [suggestionsBusy, setSuggestionsBusy] = useState(false)
  const [suggestionsError, setSuggestionsError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [busy, setBusy] = useState(false)

  const scrollRef = useRef(null)
  const contextRef = useRef(null)
  const requestRef = useRef(null)
  const lockRef = useRef(false)
  const pageRef = useRef(null)

  const contextKey = (
    `${assistantSession?.token || ''}:${conversationId || ''}`
  )
  contextRef.current = contextKey

  useEffect(() => {
    requestRef.current?.abort()
    requestRef.current = null
    lockRef.current = false
    pageRef.current = null
    setBusy(false)
    setInput('')

    return () => {
      requestRef.current?.abort()
      requestRef.current = null
      lockRef.current = false
    }
  }, [contextKey])

  useEffect(() => {
    if (!assistantSession?.token) return

    const controller = new AbortController()

    setSuggestions([])
    setSuggestionsBusy(true)
    setSuggestionsError('')

    fetch(`${API_BASE}/api/v1/business/suggestions`, {
      headers: {
        Authorization: `Bearer ${assistantSession.token}`,
      },
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 401) {
          switchAssistantUser(
            'Sample session expired. Enter the presenter PIN again.'
          )
          return null
        }

        if (!response.ok) {
          throw new Error(
            `Could not load questions (${response.status}).`
          )
        }

        return response.json()
      })
      .then((data) => {
        if (!controller.signal.aborted && data) {
          setSuggestions(data.suggestions || [])
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setSuggestionsError(
            error.message || 'Could not load questions.'
          )
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setSuggestionsBusy(false)
        }
      })

    return () => controller.abort()
  }, [assistantSession?.token, conversationId, refresh])

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, busy])

  function clearChat() {
    requestRef.current?.abort()
    requestRef.current = null
    lockRef.current = false
    pageRef.current = null
    setBusy(false)
    setMessages([])
    setInput('')
  }

  async function send(question, suggestedTarget = null) {
    const text = question?.trim()

    if (
      !text
      || lockRef.current
      || !assistantSession?.token
    ) {
      return
    }

    let plan = suggestedTarget
      ? (
        isRecordPath(suggestedTarget)
          ? { path: suggestedTarget }
          : {
            clarification:
              'This suggested record link is invalid. Refresh the questions.',
          }
      )
      : planBusinessQuestion(text)

    if (plan.page) {
      plan = pagePath(pageRef.current, plan.page)
    }

    setInput('')

    setMessages((previous) => [
      ...previous,
      {
        role: 'user',
        content: text,
        timestamp: Date.now(),
      },
    ])

    if (plan.clarification) {
      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content: plan.clarification,
          timestamp: Date.now(),
        },
      ])
      return
    }

    const key = contextKey
    const controller = new AbortController()

    requestRef.current = controller
    lockRef.current = true
    setBusy(true)

    const timer = setTimeout(
      () => controller.abort(),
      30000
    )

    try {
      const response = await fetch(
        `${API_BASE}${plan.path}`,
        {
          headers: {
            Authorization: `Bearer ${assistantSession.token}`,
          },
          cache: 'no-store',
          signal: controller.signal,
        }
      )

      if (
        controller.signal.aborted
        || contextRef.current !== key
      ) {
        return
      }

      if (response.status === 401) {
        switchAssistantUser(
          'Sample session expired. Enter the presenter PIN again.'
        )
        return
      }

      if (response.status === 403) {
        throw new Error(
          'This business area is not available to your role or license.'
        )
      }

      if (response.status === 404) {
        throw new Error(
          'Record not found or unavailable within your permitted access.'
        )
      }

      if (response.status === 422) {
        throw new Error(
          'Check the filters. Use YYYY-MM-DD for dates and YYYY-MM for payroll periods; the start date must not follow the end date.'
        )
      }

      if (!response.ok) {
        throw new Error(
          `The business service could not complete the request (${response.status}).`
        )
      }

      const result = await response.json()

      if (
        controller.signal.aborted
        || contextRef.current !== key
      ) {
        return
      }

      if (plan.kind && result.kind !== plan.kind) {
        throw new Error('Unexpected business response.')
      }

      const answer = businessAnswer(result)

      pageRef.current = Array.isArray(result.items)
        ? { path: plan.path, result }
        : null

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content: answer,
          timestamp: Date.now(),
        },
      ])
    } catch (error) {
      if (
        contextRef.current !== key
        || requestRef.current !== controller
      ) {
        return
      }

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content: error.name === 'AbortError'
            ? 'The request timed out. Please try again.'
            : (
              error.message
              || 'The business service is unavailable.'
            ),
          timestamp: Date.now(),
        },
      ])
    } finally {
      clearTimeout(timer)

      if (requestRef.current === controller) {
        requestRef.current = null
        lockRef.current = false
        setBusy(false)
      }
    }
  }

  return (
    <div className="flex-1 relative overflow-hidden flex flex-col">
      <AnimatedBackground />

      {messages.length === 0 ? (
        <div className="flex-1 min-h-0 overflow-y-auto flex flex-col items-center justify-center px-6 py-5 relative z-10">
          <motion.h1
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.5,
              ease: 'easeOut',
            }}
            className="text-[28px] font-bold mb-2 tracking-tight text-center bg-gradient-to-r from-[#1E3A8A] via-primary to-[#1E3A8A] bg-[length:200%_auto] bg-clip-text text-transparent animate-shimmer"
          >
            {greeting()}
          </motion.h1>

          <p className="text-[13.5px] text-ink-secondary mb-7 text-center max-w-md leading-relaxed">
            Ask about records allowed for your sample role.
            Results come from a fictional local snapshot.
          </p>

          <div className="w-full max-w-4xl mt-2">
            <div className="mb-3 flex items-center justify-between px-1 gap-3">
              <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                Quick actions
              </span>

              <button
                type="button"
                onClick={() => setRefresh((value) => value + 1)}
                className="inline-flex gap-1 items-center text-[11px] text-primary hover:underline"
              >
                <RotateCw className="w-3 h-3" />
                Refresh questions
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {suggestions.map((item) => {
                const kind = KINDS[item.kind] || KINDS.stock

                return (
                  <SuggestionChip
                    key={item.target}
                    icon={kind.icon}
                    label={item.question}
                    description="Available in your sample scope"
                    category={kind.label}
                    onClick={() => send(
                      item.question,
                      item.target
                    )}
                  />
                )
              })}
            </div>

            {suggestionsBusy && (
              <p
                role="status"
                className="mt-4 text-center text-xs text-ink-secondary"
              >
                Checking available records…
              </p>
            )}

            {suggestionsError && (
              <p
                role="alert"
                className="mt-4 text-center text-xs text-red-600"
              >
                {suggestionsError}
              </p>
            )}

            {!suggestionsBusy
              && !suggestionsError
              && suggestions.length < 6
              && (
                <p className="mt-4 text-center text-xs text-ink-secondary">
                  {suggestions.length} accessible records
                  available for suggestions.
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
            {messages.map((message, index) => (
              <ChatMessage
                key={index}
                role={message.role}
                content={message.content}
                timestamp={message.timestamp}
              />
            ))}

            {busy && <TypingIndicator />}
          </div>
        </div>
      )}

      <div className="relative z-10">
        <MessageInput
          onSend={send}
          disabled={busy}
          value={input}
          onValueChange={setInput}
          onClear={clearChat}
          hasMessages={messages.length > 0}
          inputPlaceholder="Ask about stock, orders, payroll, tickets or credit returns…"
          voiceEnabled={false}
        />
      </div>
    </div>
  )
}