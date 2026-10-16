import { useEffect, useRef, useState } from 'react'
import { API_BASE } from '../api.js'

const PEOPLE = [
  { id: 'demo_support', label: 'Support · Financial' },
  { id: 'demo_inventory_support', label: 'Support · Inventory' },
  { id: 'demo_implementation', label: 'Implementation · Financial and Inventory' },
]

const EXPERT_PATHS = {
  support_expert: 'support',
  implementation_expert: 'implementation',
}

const EXAMPLES = {
  support: {
    financial: 'Why would a GL voucher fail to post?',
    inventory: 'Why does inventory show negative stock?',
  },
  implementation: {
    financial: 'How do I set up a GL voucher type?',
    inventory: 'What must be configured before using inventory?',
  },
}

export default function DemoChatPage() {
  const [person, setPerson] = useState('demo_support')
  const [pin, setPin] = useState('')
  const [token, setToken] = useState(null)
  const [identity, setIdentity] = useState(null)
  const [moduleName, setModuleName] = useState('')
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const bottom = useRef(null)

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function signOut() {
    setToken(null)
    setIdentity(null)
    setModuleName('')
    setMessages([])
    setDraft('')
    setPin('')
    setError('')
  }

  async function signIn(event) {
    event.preventDefault()
    if (busy || !pin.trim()) return
    setBusy(true)
    setError('')

    try {
      const login = await fetch(`${API_BASE}/api/demo/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: person, surface: 'spia_tsplus', pin }),
      })
      if (!login.ok) throw new Error(`Session request failed (${login.status})`)
      const session = await login.json()

      const profile = await fetch(`${API_BASE}/api/demo/me`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
      if (!profile.ok) throw new Error(`Profile request failed (${profile.status})`)
      const user = await profile.json()
      if (!user.experts.some((expert) => EXPERT_PATHS[expert])) {
        throw new Error('This demo persona has no document expert yet.')
      }

      setIdentity(user)
      setToken(session.access_token)
      setModuleName(user.modules[0] || '')
      setMessages([])
    } catch (reason) {
      setError(reason.message || 'Could not start the demo session.')
    } finally {
      setPin('')
      setBusy(false)
    }
  }

  async function send(event) {
    event.preventDefault()
    const question = draft.trim()
    if (busy || !question || !token || !identity || !moduleName) return
    const expert = identity.experts.find((name) => EXPERT_PATHS[name])
    if (!expert) return

    setMessages((previous) => [...previous, { role: 'user', text: question }])
    setDraft('')
    setBusy(true)
    setError('')

    try {
      const result = await fetch(`${API_BASE}/api/demo/experts/${EXPERT_PATHS[expert]}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question, module: moduleName }),
      })
      if (result.status === 401) {
        signOut()
        setError('Session expired. Enter the demo PIN again.')
        return
      }
      if (result.status === 403) {
        setMessages((previous) => [...previous, {
          role: 'assistant', text: 'This expert or module is not licensed for this user.',
        }])
        return
      }
      if (!result.ok) throw new Error(`Expert request failed (${result.status})`)

      const answer = await result.json()
      setMessages((previous) => [...previous, {
        role: 'assistant',
        text: answer.reply,
        sources: answer.sources || [],
      }])
    } catch (reason) {
      setError(reason.message || 'The expert could not answer right now.')
    } finally {
      setBusy(false)
    }
  }

  const expert = identity?.experts.find((name) => EXPERT_PATHS[name])
  const expertPath = expert ? EXPERT_PATHS[expert] : ''
  const example = EXAMPLES[expertPath]?.[moduleName]

  return (
    <div className="min-h-screen bg-bg text-ink flex flex-col">
      <header className="bg-surface border-b border-border px-5 py-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold">SPI AI Assistant</h1>
          <p className="text-xs text-ink-secondary">Team demo · fictional SPIA users and documents</p>
        </div>
        {identity && (
          <button type="button" onClick={signOut} className="rounded-lg border border-border px-3 py-2 text-sm hover:bg-hover">
            Switch user
          </button>
        )}
      </header>

      {!identity ? (
        <main className="flex-1 grid place-items-center p-5">
          <form onSubmit={signIn} className="bg-surface border border-border rounded-2xl shadow-sm w-full max-w-md p-6 space-y-5">
            <div>
              <h2 className="text-xl font-semibold">Open a demo session</h2>
              <p className="text-sm text-ink-secondary mt-1">Choose a fictional SPIA user and enter the presenter PIN.</p>
            </div>
            <label className="block text-sm font-medium">
              Demo user
              <select value={person} onChange={(event) => setPerson(event.target.value)} className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2.5">
                {PEOPLE.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </label>
            <label className="block text-sm font-medium">
              SPIA presenter PIN
              <input type="password" autoComplete="off" value={pin} onChange={(event) => setPin(event.target.value)} className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2.5" required />
            </label>
            {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
            <button disabled={busy} className="w-full rounded-lg bg-primary px-4 py-2.5 text-white font-semibold disabled:opacity-50">
              {busy ? 'Opening…' : 'Open assistant'}
            </button>
          </form>
        </main>
      ) : (
        <main className="flex-1 min-h-0 w-full max-w-5xl mx-auto p-4 md:p-6 flex flex-col gap-4">
          <section className="bg-surface rounded-xl border border-border p-4 flex flex-wrap items-center gap-3">
            <div className="mr-auto">
              <p className="font-semibold">{identity.id}</p>
              <p className="text-sm text-ink-secondary">{expertPath === 'support' ? 'Support Expert' : 'Implementation Expert'} · {identity.surface}</p>
            </div>
            <label className="text-sm font-medium">
              Module
              <select value={moduleName} onChange={(event) => { setModuleName(event.target.value); setMessages([]) }} className="ml-2 rounded-lg border border-border bg-bg px-3 py-2">
                {identity.modules.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            </label>
          </section>

          <section className="flex-1 min-h-[280px] overflow-y-auto rounded-xl border border-border bg-surface p-4 md:p-6 space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-ink-secondary pt-10">
                <h2 className="text-xl font-semibold text-ink mb-2">Ask your licensed expert</h2>
                <p className="text-sm mb-5">Only the selected module's approved reference material is searched.</p>
                {example && <button type="button" onClick={() => setDraft(example)} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-hover">
                  Try: {example}
                </button>}
              </div>
            )}
            {messages.map((message, index) => (
              <div key={index} className={`max-w-[90%] rounded-xl px-4 py-3 text-sm whitespace-pre-wrap ${message.role === 'user' ? 'ml-auto bg-primary text-white' : 'bg-bg border border-border'}`}>
                {message.text}
                {message.sources?.length > 0 && <p className="mt-3 text-xs text-ink-secondary">Sources: {message.sources.join(', ')}</p>}
              </div>
            ))}
            {busy && <p className="text-sm text-ink-secondary">Checking the approved documents…</p>}
            <div ref={bottom} />
          </section>

          {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
          <form onSubmit={send} className="flex gap-2">
            <input value={draft} onChange={(event) => setDraft(event.target.value)} disabled={busy} maxLength={1000} placeholder={`Ask about ${moduleName}…`} className="flex-1 min-w-0 rounded-xl border border-border bg-surface px-4 py-3 text-sm" />
            <button disabled={busy || !draft.trim()} className="rounded-xl bg-primary px-5 py-3 text-white font-semibold disabled:opacity-50">Send</button>
          </form>
        </main>
      )}
    </div>
  )
}