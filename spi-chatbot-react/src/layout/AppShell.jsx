import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import TopBar from './TopBar.jsx'
import Sidebar from './Sidebar.jsx'

function makeConversation() {
  return {
    id: (crypto.randomUUID && crypto.randomUUID()) || String(Date.now() + Math.random()),
    title: 'New chat',
    messages: [],
  }
}

export default function AppShell() {
  const [collapsed, setCollapsed] = useState(false)
  const [conversations, setConversations] = useState(() => [makeConversation()])
  const [activeId, setActiveId] = useState(() => conversations[0].id)

  const activeConversation = conversations.find((c) => c.id === activeId) || conversations[0]

  function newChat() {
    const conv = makeConversation()
    setConversations((prev) => [conv, ...prev])
    setActiveId(conv.id)
  }

  function selectChat(id) {
    setActiveId(id)
  }

  // Matches React's setState updater signature — the chat page can call
  // setMessages(prev => [...prev, newMessage]) exactly like a normal
  // useState setter, it just updates the active conversation's slot
  // instead of a standalone variable.
  function setActiveMessages(updater) {
    setConversations((prev) =>
      prev.map((c) => {
        if (c.id !== activeId) return c
        const newMessages = typeof updater === 'function' ? updater(c.messages) : updater
        const title =
          c.title === 'New chat' && newMessages.length > 0
            ? newMessages[0].content.slice(0, 42)
            : c.title
        return { ...c, messages: newMessages, title }
      })
    )
  }

  return (
    <div className="h-screen flex flex-col bg-bg">
      <TopBar />
      <div className="flex-1 flex min-h-0">
        <Sidebar
          collapsed={collapsed}
          onToggle={() => setCollapsed((v) => !v)}
          conversations={conversations}
          activeId={activeId}
          onNewChat={newChat}
          onSelectChat={selectChat}
        />
        <main className="flex-1 min-w-0 flex flex-col">
          <Outlet context={{ messages: activeConversation.messages, setMessages: setActiveMessages }} />
        </main>
      </div>
    </div>
  )
}
