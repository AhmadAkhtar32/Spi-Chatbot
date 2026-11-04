import { useEffect, useId, useRef, useState } from 'react'
import { API_BASE } from '../api/client.js'

const endpoint = `${API_BASE}/api/v1/bug-reports`

export default function ReportSoftwareBug({ token }) {
  const summaryId = useId()
  const submitting = useRef(false)
  const [available, setAvailable] = useState(false)
  const [open, setOpen] = useState(false)
  const [summary, setSummary] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [reference, setReference] = useState('')

  useEffect(() => {
    if (!token) return

    const controller = new AbortController()

    async function checkAvailability() {
      try {
        const response = await fetch(endpoint, {
          cache: 'no-store',
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        })
        if (!response.ok) return
        const result = await response.json()
        if (!controller.signal.aborted) {
          setAvailable(result.available === true)
        }
      } catch {
        // Leave the action hidden if availability cannot be verified.
      }
    }

    checkAvailability()
    return () => controller.abort()
  }, [token])

  async function submit(event) {
    event.preventDefault()
    const text = summary.trim()
    if (submitting.current || !text || text.length > 500) return

    submitting.current = true
    setBusy(true)
    setError('')

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ summary: text }),
      })
      const result = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          typeof result?.detail === 'string'
            ? result.detail
            : `Could not save the report (${response.status}).`
        )
      }
      if (typeof result?.reference !== 'string') {
        throw new Error('No ticket reference was returned. Check with Support before resubmitting.')
      }

      setReference(result.reference)
      setSummary('')
    } catch (failure) {
      setError(
        failure instanceof TypeError
          ? 'Could not confirm whether the report was saved. Check with Support before resubmitting.'
          : failure.message || 'Could not save the report.'
      )
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  function close() {
    setOpen(false)
    setSummary('')
    setError('')
    setReference('')
  }

  if (!available) return null

  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        className="font-semibold text-primary hover:underline"
      >
        Report software bug
      </button>

      {open && (
        <section
          aria-label="Software bug report"
          className="absolute right-0 top-full z-50 mt-2 w-72 max-w-[85vw] rounded-lg border border-border bg-surface p-4 text-left shadow-lg"
        >
          {reference ? (
            <>
              <p role="status" className="break-all">
                Report saved. Reference: <strong>{reference}</strong>
              </p>
              <button
                type="button"
                onClick={close}
                className="mt-3 font-semibold text-primary"
              >
                Done
              </button>
            </>
          ) : (
            <form onSubmit={submit}>
              <label htmlFor={summaryId} className="block font-semibold">
                What went wrong?
              </label>
              <textarea
                id={summaryId}
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                rows={4}
                maxLength={500}
                required
                disabled={busy}
                placeholder="What did you do, and what happened?"
                className="mt-2 w-full resize-y rounded-md border border-border bg-surface p-2"
              />
              {error && <p role="alert" className="mt-2">{error}</p>}
              <div className="mt-3 flex justify-end gap-3">
                <button type="button" onClick={close} disabled={busy}>
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={busy || !summary.trim()}
                  className="font-semibold text-primary disabled:opacity-50"
                >
                  {busy ? 'Saving…' : 'Submit report'}
                </button>
              </div>
            </form>
          )}
        </section>
      )}
    </div>
  )
}