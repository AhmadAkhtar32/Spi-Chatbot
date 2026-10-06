import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import TopBar from './TopBar.jsx'
import Sidebar from './Sidebar.jsx'

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

export default function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()

  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  const [conversations, setConversations] = useState(loadConversations)

  const [activeId, setActiveId] = useState(() => {
    try {
      const savedId = localStorage.getItem(ACTIVE_CHAT_KEY)

      if (
        savedId &&
        conversations.some((conversation) => conversation.id === savedId)
      ) {
        return savedId
      }
    } catch {
      // ignore storage errors
    }

    return conversations[0]?.id ?? null
  })

  const activeConversation =
    conversations.find((conversation) => conversation.id === activeId) ??
    conversations[0]

  // Close mobile sidebar on Escape
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

  // Close mobile drawer whenever page changes
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  // Save conversations
  useEffect(() => {
    try {
      localStorage.setItem(
        CONVERSATIONS_KEY,
        JSON.stringify(conversations)
      )
    } catch {
      // ignore storage errors
    }
  }, [conversations])

  // Save active chat
  useEffect(() => {
    if (!activeId) return

    try {
      localStorage.setItem(ACTIVE_CHAT_KEY, activeId)
    } catch {
      // ignore storage errors
    }
  }, [activeId])

  // Keep active chat valid
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
    // If current chat is already empty,
    // don't create another duplicate "New chat"
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

  return (
    <div className="h-screen-dvh w-full flex flex-col bg-bg text-ink overflow-hidden">
      <TopBar
        onMenuClick={() => setMobileOpen(true)}
      />

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
          <Outlet
            context={{
              conversationId: activeConversation?.id ?? null,
              messages: activeConversation?.messages ?? [],
              setMessages: setActiveMessages,
            }}
          />
        </main>
      </div>
    </div>
  )
}