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
import { API_BASE } from '../api.js'

const KINDS = {
  stock: { label: 'Inventory', icon: Package },
  sales_orders: { label: 'Sales', icon: ShoppingCart },
  purchase_orders: { label: 'Purchasing', icon: Truck },
  credit_return_notes: { label: 'Returns', icon: FileText },
  payroll: { label: 'Payroll', icon: Wallet },
  tickets: { label: 'Support', icon: LifeBuoy },
}

const TARGET =
  /^\/api\/demo\/business\/(?:stock\/[A-Za-z0-9-]{1,64}\/[A-Za-z0-9-]{1,64}|(?:sales-orders|purchase-orders|credit-return-notes|payroll|tickets)\/[A-Za-z0-9-]{1,64})$/

function greeting() {
  const hour = new Date().getHours()

  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'

  return 'Good evening'
}

function targetFromText(text) {
  const upper = text.toUpperCase()
  const sku = upper.match(/\bSKU-[0-9]+\b/g) || []
  const warehouse =
    upper.match(/\bWH-[A-Z0-9-]+\b/g) || []
  const ids =
    upper.match(
      /\b(?:SO|PO|CRN|PAY|TCK)-[A-Z0-9-]+\b/g
    ) || []

  if (
    sku.length === 1 &&
    warehouse.length === 1 &&
    ids.length === 0
  ) {
    return (
      `/api/demo/business/stock/` +
      `${sku[0]}/${warehouse[0]}`
    )
  }

  if (
    ids.length !== 1 ||
    sku.length ||
    warehouse.length
  ) {
    return null
  }

  const id = ids[0]

  const segment = {
    SO: 'sales-orders',
    PO: 'purchase-orders',
    CRN: 'credit-return-notes',
    PAY: 'payroll',
    TCK: 'tickets',
  }[id.split('-')[0]]

  return segment
    ? `/api/demo/business/${segment}/${id}`
    : null
}

function answerFromRecord(result) {
  const record = result.record
  const details = result.details || {}
  let answer

  switch (result.kind) {
    case 'stock':
      answer =
        `${details.item_name || record.item_id} ` +
        `(${record.item_id}) in ` +
        `${details.warehouse_name || record.warehouse_id}: ` +
        `**${record.quantity_available} ` +
        `${details.unit || 'units'} available**.`
      break

    case 'sales_orders':
      answer =
        `Sales order **${record.id}** is ` +
        `**${record.status}**. Customer: ` +
        `${details.party_name || record.customer_party_id} ` +
        `(${record.customer_party_id}). Total: PKR ` +
        `${record.total_amount_pkr.toLocaleString()}.`
      break

    case 'purchase_orders':
      answer =
        `Purchase order **${record.id}** is ` +
        `**${record.status}**. Supplier: ` +
        `${details.party_name || record.supplier_party_id} ` +
        `(${record.supplier_party_id}). Total: PKR ` +
        `${record.total_amount_pkr.toLocaleString()}.`
      break

    case 'credit_return_notes':
      answer =
        `Credit return note **${record.id}** is ` +
        `**${record.status}** for sales order ` +
        `${record.sales_order_id}. Customer: ` +
        `${details.party_name || record.customer_party_id}. ` +
        `Credit: PKR ` +
        `${record.credit_amount_pkr.toLocaleString()}.`
      break

    case 'payroll':
      answer =
        `Payroll **${record.id}** for ` +
        `${record.employee_id}, period ` +
        `${record.period}: **${record.status}**. ` +
        `Net pay: PKR ${record.net.toLocaleString()}.`
      break

    case 'tickets':
      answer =
        `Support ticket **${record.id}** is ` +
        `**${record.status}**. Module: ` +
        `${record.module}. Subject: ${record.subject}.`
      break

    default:
      return (
        'The returned record type is not supported ' +
        'by this demo screen.'
      )
  }

  return (
    `${answer}\n\n` +
    `Fictional demo snapshot: ${result.snapshot_at}.`
  )
}

export default function DemoBusinessPage() {
  const {
    conversationId,
    messages,
    setMessages,
    demoSession,
    switchDemoUser,
  } = useOutletContext()

  const [input, setInput] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [suggestionsBusy, setSuggestionsBusy] =
    useState(false)
  const [suggestionsError, setSuggestionsError] =
    useState('')
  const [refresh, setRefresh] = useState(0)
  const [busy, setBusy] = useState(false)

  const scrollRef = useRef(null)
  const tokenRef = useRef(demoSession?.token)
  tokenRef.current = demoSession?.token

  useEffect(() => {
    if (!demoSession?.token) return

    const controller = new AbortController()

    setSuggestions([])
    setSuggestionsBusy(true)
    setSuggestionsError('')

    fetch(
      `${API_BASE}/api/demo/business/suggestions`,
      {
        headers: {
          Authorization:
            `Bearer ${demoSession.token}`,
        },
        cache: 'no-store',
        signal: controller.signal,
      }
    )
      .then(async (response) => {
        if (response.status === 401) {
          switchDemoUser(
            'Demo session expired. Enter the presenter PIN again.'
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
            error.message ||
              'Could not load questions.'
          )
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setSuggestionsBusy(false)
        }
      })

    return () => controller.abort()
  }, [demoSession?.token, conversationId, refresh])

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, busy])

  async function send(
    question,
    suggestedTarget = null
  ) {
    const text = question?.trim()

    if (
      !text ||
      busy ||
      !demoSession?.token
    ) {
      return
    }

    const path =
      suggestedTarget || targetFromText(text)
    const token = demoSession.token

    setInput('')
    setMessages((previous) => [
      ...previous,
      {
        role: 'user',
        content: text,
        timestamp: Date.now(),
      },
    ])

    if (!path || !TARGET.test(path)) {
      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content:
            'Enter a single record ID such as SO-1001, PO-2001, PAY-2026-09-1001, TCK-3001, or both SKU-100 and WH-LHR for stock. This demo searches approved records; it does not interpret open-ended business questions yet.',
          timestamp: Date.now(),
        },
      ])
      return
    }

    setBusy(true)

    try {
      const response = await fetch(
        `${API_BASE}${path}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
          cache: 'no-store',
        }
      )

      if (tokenRef.current !== token) return

      if (response.status === 401) {
        switchDemoUser(
          'Demo session expired. Enter the presenter PIN again.'
        )
        return
      }

      if (response.status === 403) {
        throw new Error(
          'This data area is not licensed for this user.'
        )
      }

      if (response.status === 404) {
        throw new Error(
          'Record not found or unavailable to this user.'
        )
      }

      if (!response.ok) {
        throw new Error(
          `Could not check the record (${response.status}).`
        )
      }

      const result = await response.json()

      if (tokenRef.current !== token) return

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content: answerFromRecord(result),
          timestamp: Date.now(),
        },
      ])
    } catch (error) {
      if (tokenRef.current !== token) return

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content:
            error.message ||
            'The business service is unavailable.',
          timestamp: Date.now(),
        },
      ])
    } finally {
      setBusy(false)
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
            Look up records allowed for your demo role.
            Results come from a fictional local snapshot.
          </p>

          <div className="w-full max-w-4xl mt-2">
            <div className="mb-3 flex items-center justify-between px-1 gap-3">
              <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                Quick actions
              </span>

              <button
                type="button"
                onClick={() =>
                  setRefresh((value) => value + 1)
                }
                className="inline-flex gap-1 items-center text-[11px] text-primary hover:underline"
              >
                <RotateCw className="w-3 h-3" />
                Refresh questions
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {suggestions.map((item) => {
                const kind =
                  KINDS[item.kind] || KINDS.stock

                return (
                  <SuggestionChip
                    key={item.target}
                    icon={kind.icon}
                    label={item.question}
                    description="Available in your demo scope"
                    category={kind.label}
                    onClick={() =>
                      send(item.question, item.target)
                    }
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

            {!suggestionsBusy &&
              !suggestionsError &&
              suggestions.length < 6 && (
                <p className="mt-4 text-center text-xs text-ink-secondary">
                  {suggestions.length} accessible
                  records available for suggestions.
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
          onClear={() => {
            setMessages([])
            setInput('')
          }}
          hasMessages={messages.length > 0}
          inputPlaceholder="Enter an order, stock, payroll, return, or ticket ID…"
          voiceEnabled={false}
        />
      </div>
    </div>
  )
}