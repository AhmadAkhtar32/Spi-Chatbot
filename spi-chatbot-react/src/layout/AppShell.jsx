import ReportSoftwareBug from '../components/ReportSoftwareBug.jsx'
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

import usePersonalHistory from '../services/usePersonalHistory.js'
import TopBar from './TopBar.jsx'
import Sidebar from './Sidebar.jsx'
import { API_BASE } from '../api/client.js'

export default function AppShell({ licensedMode = false }) {
  const navigate = useNavigate()
  const location = useLocation()

  const [scrollHeaders, setScrollHeaders] = useState(null)

  function renderIdentityHeader(content) {
    return scrollHeaders?.identity
      ? createPortal(content, scrollHeaders.identity)
      : content
  }

  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  const [selectedPerson, setSelectedPerson] = useState('demo_support')
  const [presenterPin, setPresenterPin] = useState('')
  const [assistantSession, setAssistantSession] = useState(null)
  const [sessionError, setSessionError] = useState('')
  const [openingSession, setOpeningSession] = useState(false)

  const history = usePersonalHistory(assistantSession, switchAssistantUser)
  const conversations = history.chats, activeId = history.active, activeConversation = history.activeChat
  const setActiveMessages = history.setMessages

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

  function newChat() { history.newChat(); setMobileOpen(false); navigate('/') }
  function selectChat(id) { history.selectChat(id).catch(e => history.setError(e.message)); setMobileOpen(false); navigate('/') }
  function resetAssistantChats() { history.newChat() }

  function switchAssistantUser(message = '') {
    setAssistantSession(null)
    setPresenterPin('')
    setSessionError(message)
    resetAssistantChats()
    navigate('/')
  }

  async function openAssistant(event) {
    event.preventDefault()
    if (openingSession || !presenterPin.trim()) return

    setOpeningSession(true)
    setSessionError('')

    try {
      const login = await fetch(`${API_BASE}/api/v1/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
        body: JSON.stringify({
          user_id: selectedPerson,
          surface: 'spia_tsplus',
          pin: presenterPin,
        }),
      })

      if (!login.ok) {
        if (login.status === 401) {
          throw new Error(
            'Incorrect presenter PIN or unavailable sample user.'
          )
        }

        if (login.status === 404) {
          throw new Error(
            'Enable sample sessions in the backend and restart it.'
          )
        }

        throw new Error(
          `Could not open sample session (${login.status}).`
        )
      }

      const { access_token: token } = await login.json()

      const profile = await fetch(`${API_BASE}/api/v1/me`, {
        cache: 'no-store',
        headers: { Authorization: `Bearer ${token}` },
      })

      if (!profile.ok) {
        throw new Error(
          `Could not load the sample user (${profile.status}).`
        )
      }

      const user = await profile.json()

      const accessResponse = await fetch(`${API_BASE}/api/v1/access`, {
        cache: 'no-store',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!accessResponse.ok) {
        throw new Error('Could not verify current access.')
      }
      const access = await accessResponse.json()
      if (!access.active_pairs?.length) {
        throw new Error('No active feature is assigned.')
      }

      resetAssistantChats()
      setAssistantSession({ token, user })
    } catch (error) {
      setSessionError(
        error.message || 'Could not open the assistant.'
      )
    } finally {
      setPresenterPin('')
      setOpeningSession(false)
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
          history={history}
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
          {licensedMode && !assistantSession ? (
            <div className="flex-1 overflow-y-auto grid place-items-center p-5">
              <form
                onSubmit={openAssistant}
                className="card w-full max-w-md p-6 space-y-5"
              >
                <div>
                  <h1 className="text-xl font-semibold">
                    Open the assistant
                  </h1>
                  <p className="text-sm text-ink-secondary mt-1">
                    Choose a fictional SPIA user and enter the
                    presenter PIN.
                  </p>
                </div>

                <label className="block text-sm font-medium">
                  Presentation profile
                  <select
                    value={selectedPerson}
                    onChange={(event) =>
                      setSelectedPerson(event.target.value)
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
                    value={presenterPin}
                    onChange={(event) =>
                      setPresenterPin(event.target.value)
                    }
                    className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2.5"
                    required
                  />
                </label>

                {sessionError && (
                  <p
                    role="alert"
                    className="text-sm text-red-600"
                  >
                    {sessionError}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={openingSession}
                  className="w-full rounded-lg bg-primary px-4 py-2.5 text-white font-semibold disabled:opacity-50"
                >
                  {openingSession ? 'Opening…' : 'Open assistant'}
                </button>
              </form>
            </div>
          ) : (
            <>
              {licensedMode && renderIdentityHeader(
                <div className="shrink-0 border-b border-border bg-surface px-4 py-2 flex items-center justify-between gap-3 text-xs text-ink-secondary">
                  <span className="truncate">
                    Internal presentation ·{' '}
                    {assistantSession.user.role.replace(/_/g, ' ')}
                  </span>

                  <div className="flex shrink-0 items-center gap-3">
                    <ReportSoftwareBug
                      key={assistantSession.token}
                      token={assistantSession.token}
                    />
                    <button
                      type="button"
                      onClick={() => switchAssistantUser()}
                      className="text-primary font-semibold whitespace-nowrap hover:underline"
                    >
                      Switch user
                    </button>
                  </div>
                </div>
              )}

              <Outlet
                context={{
                  conversationId:
                    activeConversation?.id ?? null,
                  messages:
                    activeConversation?.messages ?? [],
                  history,
                  setMessages: setActiveMessages,
                  assistantSession,
                  switchAssistantUser,
                  resetAssistantChats,
                  scrollHeaders,
                  setScrollHeaders,
                }}
              />
            </>
          )}
        </main>
      </div>
    </div>
  )
}
