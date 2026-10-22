import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

import TopBar from './TopBar.jsx'
import Sidebar from './Sidebar.jsx'
import { API_BASE } from '../api.js'

const CONVERSATIONS_KEY = 'spi-conversations'
const ACTIVE_CHAT_KEY = 'spi-active-chat'

function makeConversation() {
  return {
    id:
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : String(Date.now() + Math.random()),
    title: 'New chat',
    messages: [],
  }
}

function loadConversations() {
  try {
    const saved = localStorage.getItem(CONVERSATIONS_KEY)

    if (!saved) {
      return [makeConversation()]
    }

    const parsed = JSON.parse(saved)

    if (!Array.isArray(parsed) || parsed.length === 0) {
      return [makeConversation()]
    }

    return parsed
  } catch {
    return [makeConversation()]
  }
}

export default function AppShell({ demoMode = false }) {
  const navigate = useNavigate()
  const location = useLocation()

  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  // Demo chats stay in memory, including when a presenter changes users.
  const [conversations, setConversations] = useState(() =>
    demoMode ? [makeConversation()] : loadConversations()
  )

  const [demoPerson, setDemoPerson] = useState('demo_support')
  const [demoPin, setDemoPin] = useState('')
  const [demoSession, setDemoSession] = useState(null)
  const [demoError, setDemoError] = useState('')
  const [openingDemo, setOpeningDemo] = useState(false)

  const [activeId, setActiveId] = useState(() => {
    try {
      const savedId = demoMode
        ? null
        : localStorage.getItem(ACTIVE_CHAT_KEY)

      if (
        savedId &&
        conversations.some(
          (conversation) => conversation.id === savedId
        )
      ) {
        return savedId
      }
    } catch {
      // Ignore storage errors.
    }

    return conversations[0]?.id ?? null
  })

  const activeConversation =
    conversations.find(
      (conversation) => conversation.id === activeId
    ) ?? conversations[0]

  useEffect(() => {
    function handleEscape(event) {
      if (event.key === 'Escape') {
        setMobileOpen(false)
      }
    }

    window.addEventListener('keydown', handleEscape)

    return () => {
      window.removeEventListener('keydown', handleEscape)
    }
  }, [])

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (demoMode) return

    try {
      localStorage.setItem(
        CONVERSATIONS_KEY,
        JSON.stringify(conversations)
      )
    } catch {
      // Ignore storage errors.
    }
  }, [conversations, demoMode])

  useEffect(() => {
    if (demoMode || !activeId) return

    try {
      localStorage.setItem(ACTIVE_CHAT_KEY, activeId)
    } catch {
      // Ignore storage errors.
    }
  }, [activeId, demoMode])

  useEffect(() => {
    if (conversations.length === 0) {
      const conversation = makeConversation()
      setConversations([conversation])
      setActiveId(conversation.id)
      return
    }

    const exists = conversations.some(
      (conversation) => conversation.id === activeId
    )

    if (!exists) {
      setActiveId(conversations[0].id)
    }
  }, [conversations, activeId])

  function newChat() {
    if (
      activeConversation &&
      activeConversation.messages.length === 0 &&
      activeConversation.title === 'New chat'
    ) {
      setMobileOpen(false)
      navigate('/')
      return
    }

    const conversation = makeConversation()

    setConversations((previous) => [
      conversation,
      ...previous,
    ])
    setActiveId(conversation.id)
    setMobileOpen(false)
    navigate('/')
  }

  function selectChat(chatId) {
    const exists = conversations.some(
      (conversation) => conversation.id === chatId
    )

    if (!exists) return

    setActiveId(chatId)
    setMobileOpen(false)
    navigate('/')
  }

  function setActiveMessages(updater) {
    setConversations((previous) =>
      previous.map((conversation) => {
        if (conversation.id !== activeId) {
          return conversation
        }

        const newMessages =
          typeof updater === 'function'
            ? updater(conversation.messages)
            : updater

        const safeMessages = Array.isArray(newMessages)
          ? newMessages
          : []

        let title = conversation.title

        if (
          conversation.title === 'New chat' &&
          safeMessages.length > 0
        ) {
          const firstMessage = safeMessages[0]?.content

          if (
            typeof firstMessage === 'string' &&
            firstMessage.trim()
          ) {
            title = firstMessage
              .trim()
              .replace(/\s+/g, ' ')
              .slice(0, 42)
          }
        }

        return {
          ...conversation,
          messages: safeMessages,
          title,
        }
      })
    )
  }

  function resetDemoChats() {
    if (!demoMode) return

    const first = makeConversation()
    setConversations([first])
    setActiveId(first.id)
  }

  function switchDemoUser(message = '') {
    setDemoSession(null)
    setDemoPin('')
    setDemoError(message)
    resetDemoChats()
    navigate('/')
  }

  async function openDemo(event) {
    event.preventDefault()
    if (openingDemo || !demoPin.trim()) return

    setOpeningDemo(true)
    setDemoError('')

    try {
      const login = await fetch(`${API_BASE}/api/demo/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
        body: JSON.stringify({
          user_id: demoPerson,
          surface: 'spia_tsplus',
          pin: demoPin,
        }),
      })

      if (!login.ok) {
        if (login.status === 401) {
          throw new Error(
            'Incorrect presenter PIN or unavailable demo user.'
          )
        }

        if (login.status === 404) {
          throw new Error(
            'Enable demo sessions in the backend and restart it.'
          )
        }

        throw new Error(
          `Could not open demo session (${login.status}).`
        )
      }

      const { access_token: token } = await login.json()

      const profile = await fetch(`${API_BASE}/api/demo/me`, {
        cache: 'no-store',
        headers: { Authorization: `Bearer ${token}` },
      })

      if (!profile.ok) {
        throw new Error(
          `Could not load the demo user (${profile.status}).`
        )
      }

      const user = await profile.json()

      const hasExpert = user.experts?.some(
        (name) =>
          name === 'support_expert' ||
          name === 'implementation_expert'
      )

      const hasBusinessData = user.permissions?.some(
        (name) =>
          [
            'stock.read',
            'sales_orders.read',
            'purchase_orders.read',
            'tickets.read',
            'payroll.read',
            'payroll.read_self',
          ].includes(name)
      )

      if (
        (!hasExpert && !hasBusinessData) ||
        !user.modules?.length
      ) {
        throw new Error(
          'This demo user has no available expert or business data.'
        )
      }

      resetDemoChats()
      setDemoSession({ token, user })
    } catch (error) {
      setDemoError(
        error.message || 'Could not open the assistant.'
      )
    } finally {
      setDemoPin('')
      setOpeningDemo(false)
    }
  }

  return (
    <div className="h-screen-dvh w-full flex flex-col bg-bg text-ink overflow-hidden">
      <TopBar onMenuClick={() => setMobileOpen(true)} />

      <div className="flex-1 flex min-h-0 relative">
        {mobileOpen && (
          <div
            className="fixed inset-0 z-40 bg-slate-950/50 backdrop-blur-[1px] md:hidden"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
        )}

        <Sidebar
          collapsed={collapsed}
          onToggle={() => setCollapsed((value) => !value)}
          mobileOpen={mobileOpen}
          onMobileClose={() => setMobileOpen(false)}
          conversations={conversations}
          activeId={activeId}
          onNewChat={newChat}
          onSelectChat={selectChat}
        />

        <main className="flex-1 min-w-0 min-h-0 flex flex-col bg-bg">
          {demoMode && !demoSession ? (
            <div className="flex-1 overflow-y-auto grid place-items-center p-5">
              <form
                onSubmit={openDemo}
                className="card w-full max-w-md p-6 space-y-5"
              >
                <div>
                  <h1 className="text-xl font-semibold">
                    Open a demo session
                  </h1>
                  <p className="text-sm text-ink-secondary mt-1">
                    Choose a fictional SPIA user and enter the
                    presenter PIN.
                  </p>
                </div>

                <label className="block text-sm font-medium">
                  Demo user
                  <select
                    value={demoPerson}
                    onChange={(event) =>
                      setDemoPerson(event.target.value)
                    }
                    className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2.5"
                  >
                    <option value="demo_support">
                      Support · Financial
                    </option>
                    <option value="demo_inventory_support">
                      Support · Inventory
                    </option>
                    <option value="demo_implementation">
                      Implementation · Financial and Inventory
                    </option>
                    <option value="demo_operations">
                      Operations · Stock and orders
                    </option>
                    <option value="demo_dual_party">
                      Partner · Customer and supplier
                    </option>
                    <option value="demo_employee">
                      Employee · Own payroll
                    </option>
                    <option value="demo_hr">
                      HR · Payroll
                    </option>
                    <option value="demo_bi">
                      Internal BI · Analytics
                    </option>
                    <option value="demo_document_clerk">
                      Document clerk · Source data preview
                    </option>
                  </select>
                </label>

                <label className="block text-sm font-medium">
                  SPIA presenter PIN
                  <input
                    type="password"
                    autoComplete="off"
                    value={demoPin}
                    onChange={(event) =>
                      setDemoPin(event.target.value)
                    }
                    className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2.5"
                    required
                  />
                </label>

                {demoError && (
                  <p
                    role="alert"
                    className="text-sm text-red-600"
                  >
                    {demoError}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={openingDemo}
                  className="w-full rounded-lg bg-primary px-4 py-2.5 text-white font-semibold disabled:opacity-50"
                >
                  {openingDemo ? 'Opening…' : 'Open assistant'}
                </button>
              </form>
            </div>
          ) : (
            <>
              {demoMode && (
                <div className="shrink-0 border-b border-border bg-surface px-4 py-2 flex items-center justify-between gap-3 text-xs text-ink-secondary">
                  <span className="truncate">
                    Team demo · {demoSession.user.id} ·{' '}
                    {demoSession.user.role.replace(/_/g, ' ')}
                  </span>

                  <button
                    type="button"
                    onClick={() => switchDemoUser()}
                    className="text-primary font-semibold whitespace-nowrap hover:underline"
                  >
                    Switch user
                  </button>
                </div>
              )}

              <Outlet
                context={{
                  conversationId:
                    activeConversation?.id ?? null,
                  messages:
                    activeConversation?.messages ?? [],
                  setMessages: setActiveMessages,
                  demoSession,
                  switchDemoUser,
                  resetDemoChats,
                }}
              />
            </>
          )}
        </main>
      </div>
    </div>
  )
}