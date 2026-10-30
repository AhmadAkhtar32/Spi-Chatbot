import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import ChatMessage from '../components/ChatMessage.jsx'
import MessageInput from '../components/MessageInput.jsx'
import TypingIndicator from '../components/TypingIndicator.jsx'
import { API_BASE } from '../api/client.js'

const ROOT = '/api/v1/experts/project-knowledge'

export default function ProjectKnowledgeExpertPage() {
  const {
    assistantSession,
    switchAssistantUser,
    conversationId,
  } = useOutletContext()

  const token = assistantSession?.token

  const [caps, setCaps] = useState(null)
  const [sources, setSources] = useState([])
  const [receipts, setReceipts] = useState([])
  const [selected, setSelected] = useState('')
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [checking, setChecking] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const alive = useRef(false)
  const pending = useRef(new Set())
  const answer = useRef(null)
  const generation = useRef(0)
  const manifest = useRef(null)
  const fileInput = useRef(null)
  const scroll = useRef(null)

  function clearChat() {
    answer.current?.abort()
    answer.current = null
    setLoading(false)
    setMessages([])
    setText('')
  }

  async function request(path, controller, options = {}) {
    const response = await fetch(`${API_BASE}${ROOT}${path}`, {
      ...options,
      cache: 'no-store',
      signal: controller.signal,
      headers: {
        ...options.headers,
        Authorization: `Bearer ${token}`,
      },
    })

    const data = await response.json().catch(() => ({}))

    if (
      response.status === 401 &&
      alive.current &&
      !controller.signal.aborted
    ) {
      switchAssistantUser(
        'Session expired. Please open the assistant again.'
      )
    }

    if (!response.ok) {
      const failure = new Error(
        typeof data.detail === 'string'
          ? data.detail
          : `Request failed (${response.status}).`
      )

      failure.status = response.status
      throw failure
    }

    return data
  }

  async function refresh() {
    const sequence = ++generation.current
    const controller = new AbortController()

    pending.current.add(controller)
    setChecking(true)

    try {
      const capabilities = await request(
        '/capabilities',
        controller
      )

      let approved = {
        sources: [],
        knowledge_version: '',
      }

      try {
        approved = await request('/sources', controller)
      } catch (failure) {
        if (failure.status !== 403) throw failure
      }

      const uploads = capabilities.can_list_uploads
        ? await request('/documents', controller)
        : { documents: [] }

      if (
        !alive.current ||
        controller.signal.aborted ||
        sequence !== generation.current
      ) {
        return
      }

      const next = {
        revision: capabilities.access_revision,
        version: approved.knowledge_version,
      }

      if (
        manifest.current &&
        JSON.stringify(manifest.current) !== JSON.stringify(next)
      ) {
        clearChat()
        setNotice(
          'Available knowledge or permissions changed. Conversation cleared.'
        )
      }

      manifest.current = next

      setCaps(capabilities)
      setSources(approved.sources)
      setReceipts(uploads.documents)

      setSelected(previous =>
        approved.sources.some(item => item.source === previous)
          ? previous
          : approved.sources[0]?.source || ''
      )

      setError('')
    } catch (failure) {
      if (
        alive.current &&
        !controller.signal.aborted &&
        sequence === generation.current
      ) {
        clearChat()
        manifest.current = null
        setCaps(null)
        setSources([])
        setReceipts([])
        setSelected('')
        setError(failure.message)
      }
    } finally {
      pending.current.delete(controller)

      if (
        alive.current &&
        sequence === generation.current
      ) {
        setChecking(false)
      }
    }
  }

  useEffect(() => {
    alive.current = true
    refresh()

    const timer = setInterval(refresh, 30000)
    window.addEventListener('focus', refresh)

    return () => {
      alive.current = false
      generation.current += 1
      clearInterval(timer)
      window.removeEventListener('focus', refresh)

      pending.current.forEach(controller => controller.abort())
      answer.current?.abort()
    }
  }, [token])

  useEffect(() => {
    clearChat()
  }, [conversationId])

  useEffect(() => {
    scroll.current?.scrollTo({
      top: scroll.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, loading])

  async function upload(event) {
    const file = event.target.files?.[0]
    event.target.value = ''

    if (!file || uploading || !caps?.can_upload) return
    setNotice('')
    setError('')

    if (
      !file.name.toLowerCase().endsWith('.txt') ||
      !file.size ||
      file.size > 2 * 1024 * 1024
    ) {
      setError(
        'Choose a nonempty UTF-8 TXT file, at most 2 MiB.'
      )
      return
    }

    const controller = new AbortController()
    pending.current.add(controller)

    setUploading(true)
    setError('')

    try {
      const result = await request(
        `/documents?filename=${encodeURIComponent(file.name)}`,
        controller,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'text/plain; charset=utf-8',
          },
          body: file,
        }
      )

      if (!alive.current || controller.signal.aborted) return

      setNotice(
        `Uploaded ${result.document.source}. Pending administrator review; not available for questions yet.`
      )

      await refresh()
    } catch (failure) {
      if (alive.current && !controller.signal.aborted) {
        setError(failure.message)
      }
    } finally {
      pending.current.delete(controller)
      if (alive.current) setUploading(false)
    }
  }

  async function send(question) {
    if (
      !selected ||
      !caps ||
      checking ||
      answer.current
    ) {
      return
    }

    if (question.length > 1000) {
      setError(
        'Use at most 1,000 characters for a question.'
      )
      return
    }

    const controller = new AbortController()
    answer.current = controller
    pending.current.add(controller)

    const version = manifest.current?.version

    setLoading(true)
    setError('')

    setMessages(previous => [
      ...previous,
      {
        role: 'user',
        content: question,
        timestamp: Date.now(),
      },
    ])

    try {
      const result = await request('', controller, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question,
          source: selected,
        }),
      })

      if (!alive.current || controller.signal.aborted) return

      if (
        manifest.current?.version !== version ||
        result.knowledge_version !== version
      ) {
        clearChat()
        setNotice(
          'Knowledge changed. Refresh and ask again.'
        )
        await refresh()
        return
      }

      setMessages(previous => [
        ...previous,
        {
          role: 'assistant', content: result.reply, timestamp: Date.now(),
        language: result.language, translation_proof: result.translation_proof, raw_sources: result.sources,
          sources: result.sources.map(source => {
            const item = sources.find(
              candidate => candidate.source === source
            )

            return item
              ? `${item.name} (${item.id.slice(0, 8)})`
              : source
          }),
        },
      ])
    } catch (failure) {
      if (alive.current && !controller.signal.aborted) {
        if ([401, 403, 503].includes(failure.status)) {
          clearChat()
          setCaps(null)
          setSources([])
        }

        setError(failure.message)
      }
    } finally {
      pending.current.delete(controller)

      if (answer.current === controller) {
        answer.current = null
      }

      if (alive.current && !answer.current) {
        setLoading(false)
      }
    }
  }

  return (
    <section
      className="spia-company-knowledge flex-1 min-h-0 min-w-0 flex flex-col overflow-hidden"
      aria-label="Project Knowledge"
    >
      <header className="shrink-0 border-b border-border bg-surface px-4 py-3 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-sm font-semibold">
            Project Knowledge
          </h1>

          <div className="flex items-center gap-3 text-xs">
            <button
              type="button"
              className="text-primary disabled:opacity-50"
              disabled={checking || uploading}
              onClick={refresh}
            >
              {checking ? 'Checking access?' : 'Refresh documents'}
            </button>

            {caps?.can_upload && (
              <button
                type="button"
                className="rounded-md border border-border px-3 py-1.5 text-primary disabled:opacity-50"
                disabled={checking || uploading}
                onClick={() => fileInput.current?.click()}
              >
                {uploading ? 'Uploading?' : 'Upload TXT'}
              </button>
            )}

            <input
              ref={fileInput}
              type="file"
              accept=".txt,text/plain"
              className="hidden"
              onChange={upload}
            />

            {caps?.can_list_uploads && (
              <details className="relative">
                <summary className="cursor-pointer text-ink-secondary rounded-md px-1 py-1.5 focus-visible:outline-primary">
                  Uploads ({receipts.length})
                </summary>

                <div className="absolute right-0 top-full z-20 mt-2 w-64 max-w-[80vw] rounded-lg border border-border bg-surface p-3 shadow-lg">
                  <p className="mb-2 font-semibold">
                    Your uploads
                  </p>

                  <div className="max-h-[30dvh] overflow-y-auto space-y-2">
                    {!receipts.length && (
                      <p className="text-ink-secondary">
                        No uploads yet.
                      </p>
                    )}

                    {receipts.map(item => (
                      <div
                        key={item.id}
                        className="border-b border-border pb-2 last:border-0"
                      >
                        <p className="break-words font-medium">
                          {item.source}
                        </p>

                        <p className="mt-0.5 capitalize text-ink-secondary">
                          {item.status.replaceAll('_', ' ')}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </details>
            )}
          </div>
        </div>

        <div className="mt-2 flex items-center gap-3">
          <label
            htmlFor="company-knowledge-source"
            className="shrink-0 text-xs text-ink-secondary"
          >
            Document
          </label>

          <select
            id="company-knowledge-source"
            value={selected}
            disabled={checking || !sources.length}
            className="min-w-0 flex-1 rounded-md border border-border bg-bg px-3 py-2 text-sm text-ink focus:outline-none focus:border-primary disabled:opacity-60"
            onChange={event => {
              clearChat()
              setSelected(event.target.value)
              setError('')
            }}
          >
            {!sources.length && (
              <option value="">
                No documents available for your access
              </option>
            )}

            {sources.map(item => (
              <option key={item.id} value={item.source}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
      </header>

      <div
        ref={scroll}
        className="flex-1 min-h-0 overflow-y-auto overscroll-contain"
        role="region"
        aria-label="Document conversation"
        tabIndex={0}
      >
        <div className="max-w-3xl mx-auto px-4 py-5 sm:px-6 space-y-4">
          {notice && (
            <p
              className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-ink-secondary"
              role="status"
            >
              {notice}
            </p>
          )}

          {error && (
            <p
              className="rounded-lg border border-danger/30 px-3 py-2 text-sm text-danger"
              role="alert"
            >
              {error}
            </p>
          )}

          {!messages.length && !error && (
            <div className="py-8 text-center">
              <h2 className="text-lg font-semibold">
                Ask about your company documents
              </h2>

              <p className="mt-2 text-sm text-ink-secondary">
                {selected
                  ? 'Ask a question about the selected document.'
                  : checking
                    ? 'Checking your document access?'
                    : 'No approved document is assigned to you yet.'}
              </p>
            </div>
          )}

          {messages.map((item, index) => (
            <ChatMessage key={index} {...item} translation={item.translation_proof ? {
            token,
            proof: item.translation_proof,
            expert: 'project_knowledge',
            module: 'project',
            sources: item.raw_sources || [],
            onSessionExpired: switchAssistantUser,
          } : null} />
          ))}

          {loading && <TypingIndicator />}
        </div>
      </div>

      <MessageInput
        onSend={send}
        value={text}
        onValueChange={setText}
        onClear={clearChat}
        hasMessages={!!messages.length}
        voiceEnabled={false}
        showVoiceControl={false}
        showAttachments={false}
        maxChars={1000}
        disabled={loading || checking || !selected || !caps}
        inputPlaceholder="Ask about the selected company document?"
      />
    </section>
  )
}
