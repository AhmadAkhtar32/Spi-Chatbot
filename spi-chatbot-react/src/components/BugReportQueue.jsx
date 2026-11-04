import { useEffect, useId, useRef, useState } from 'react'
import { API_BASE } from '../api/client.js'

const endpoint = `${API_BASE}/api/v1/bug-reports/queue`
const labels = {
  open: 'Open',
  in_progress: 'In progress',
  resolved: 'Resolved',
}
const transitions = {
  open: { status: 'in_progress', label: 'Start work' },
  in_progress: { status: 'resolved', label: 'Mark resolved' },
}

async function readResult(response) {
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const error = new Error(
      typeof data?.detail === 'string'
        ? data.detail
        : `Request failed (${response.status}).`
    )
    error.status = response.status
    throw error
  }
  return data
}

export default function BugReportQueue({ token }) {
  const referenceId = useId()
  const pending = useRef(false)
  const [allowed, setAllowed] = useState(false)
  const [open, setOpen] = useState(false)
  const [reference, setReference] = useState('')
  const [query, setQuery] = useState('')
  const [items, setItems] = useState([])
  const [nextOffset, setNextOffset] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (!token) return
    const controller = new AbortController()

    async function checkAccess() {
      try {
        const response = await fetch(`${endpoint}?limit=1`, {
          cache: 'no-store',
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        })
        if (!controller.signal.aborted) setAllowed(response.ok)
      } catch {
        // Keep the button hidden if the server cannot verify access.
      }
    }

    checkAccess()
    return () => controller.abort()
  }, [token])

  async function run(action) {
    if (pending.current) return
    pending.current = true
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await action()
    } catch (failure) {
      setError(failure.message || 'The queue request failed.')
    } finally {
      pending.current = false
      setBusy(false)
    }
  }

  async function load(filter, offset = 0) {
    const params = new URLSearchParams({ limit: '25', offset: String(offset) })
    if (filter) params.set('reference', filter)

    const response = await fetch(`${endpoint}?${params}`, {
      cache: 'no-store',
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await readResult(response)
    setItems(current => offset === 0 ? data.items : [...current, ...data.items])
    setQuery(filter)
    setNextOffset(data.next_offset)
  }

  function search(event) {
    event.preventDefault()
    const filter = reference.trim().toUpperCase()
    setNotice('')
    if (filter && !/^BUG-[0-9A-F]{32}$/.test(filter)) {
      setError('Paste the full BUG reference, or leave it blank to see all reports.')
      return
    }
    run(() => load(filter))
  }

  function advance(ticket) {
    const next = transitions[ticket.status]
    if (!next) return

    run(async () => {
      const response = await fetch(
        `${endpoint}/${encodeURIComponent(ticket.reference)}`,
        {
          method: 'PATCH',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            expected_status: ticket.status,
            status: next.status,
          }),
        }
      )

      let updated
      try {
        updated = await readResult(response)
      } catch (failure) {
        if (failure.status === 409) {
          await load(query)
          setNotice('The status changed. The queue has been refreshed.')
          return
        }
        throw failure
      }

      setItems(current => current.map(item =>
        item.reference === updated.reference
          ? { ...item, status: updated.status }
          : item
      ))
      setNotice(`Status updated to ${labels[updated.status]}.`)
    })
  }

  if (!allowed) return null

  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={open}
        disabled={busy}
        className="whitespace-nowrap font-semibold text-primary hover:underline"
        onClick={() => {
          if (open) {
            setOpen(false)
            return
          }
          setOpen(true)
          run(() => load(query))
        }}
      >
        Bug queue
      </button>

      {open && (
        <section
          aria-label="Internal bug queue"
          aria-busy={busy}
          className="fixed right-3 top-28 z-50 max-h-[65vh] w-[30rem] max-w-[calc(100vw-1.5rem)] overflow-auto rounded-lg border border-border bg-surface p-4 text-left shadow-lg"
        >
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold">Internal bug queue</h2>
            <button type="button" disabled={busy} onClick={() => setOpen(false)}>
              Close
            </button>
          </div>

          <form onSubmit={search} className="mt-3">
            <label htmlFor={referenceId} className="block">Ticket reference</label>
            <div className="mt-1 flex gap-2">
              <input
                id={referenceId}
                value={reference}
                onChange={event => setReference(event.target.value)}
                placeholder="Leave blank to show all"
                maxLength={36}
                disabled={busy}
                className="min-w-0 flex-1 rounded border border-border bg-surface px-2 py-1"
              />
              <button type="submit" disabled={busy} className="font-semibold text-primary">
                Search
              </button>
            </div>
          </form>

          {busy && <p role="status" className="mt-3">Working…</p>}
          {error && <p role="alert" className="mt-3">{error}</p>}
          {notice && <p role="status" className="mt-3">{notice}</p>}
          {!busy && !error && items.length === 0 && (
            <p className="mt-3">No reports found.</p>
          )}

          <ul className="mt-3 space-y-2">
            {items.map(ticket => (
              <li key={ticket.reference} className="rounded border border-border p-3">
                <p className="break-all font-semibold">{ticket.reference}</p>
                <p className="mt-1 whitespace-pre-wrap break-words">{ticket.summary}</p>
                <p className="mt-1">
                  {labels[ticket.status]} · {ticket.created_by} ·{' '}
                  {new Date(ticket.created_at).toLocaleString()}
                </p>
                {transitions[ticket.status] && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => advance(ticket)}
                    className="mt-2 font-semibold text-primary disabled:opacity-50"
                  >
                    {transitions[ticket.status].label}
                  </button>
                )}
              </li>
            ))}
          </ul>

          {nextOffset !== null && (
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => load(query, nextOffset))}
              className="mt-3 font-semibold text-primary"
            >
              Load more
            </button>
          )}
        </section>
      )}
    </div>
  )
}