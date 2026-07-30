import { useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import Navbar from './components/Navbar.jsx'
import Workspace from './components/Workspace.jsx'
import ChatWindow from './components/ChatWindow.jsx'
import MessageInput from './components/MessageInput.jsx'

export default function App() {
  const [view, setView] = useState('workspace') // 'workspace' | 'chat'
  const [messages, setMessages] = useState([]) // persisted across view switches
  const [loading, setLoading] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [activeModule, setActiveModule] = useState(null) // e.g. "Inventory"
  const [interactionId, setInteractionId] = useState(null) // ties follow-ups to the same thread

  async function handleSend(text) {
    setView('chat')
    setMessages((prev) => [...prev, { role: 'user', content: text, timestamp: Date.now() }])
    setLoading(true)
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, interaction_id: interactionId }),
      })
      const data = await res.json()
      setInteractionId(data.interaction_id ?? null)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.reply, trace: data.trace, timestamp: Date.now() },
      ])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Unable to reach the backend service. Confirm the API server is running.',
          timestamp: Date.now(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  function handleModuleSelect(moduleTitle, prompt) {
    setActiveModule(moduleTitle)
    handleSend(prompt)
  }

  function handleTaskSelect(taskText) {
    setView('chat')
    setInputValue(taskText)
  }

  function handleBack() {
    setView('workspace')
  }

  const moduleLabel =
    view === 'workspace' ? 'Workspace' : activeModule ? `${activeModule} Module` : 'AI Assistant'

  return (
    <div className="h-screen flex flex-col bg-bg">
      <Navbar moduleLabel={moduleLabel} />

      <AnimatePresence mode="wait">
        {view === 'workspace' ? (
          <Workspace key="workspace" onModuleSelect={handleModuleSelect} onTaskSelect={handleTaskSelect} />
        ) : (
          <ChatWindow key="chat" messages={messages} loading={loading} onBack={handleBack} />
        )}
      </AnimatePresence>

      <MessageInput
        onSend={handleSend}
        disabled={loading}
        value={inputValue}
        onValueChange={setInputValue}
      />
    </div>
  )
}
