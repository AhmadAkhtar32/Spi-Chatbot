import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  BrowserRouter, Routes, Route, Navigate, useOutletContext,
} from 'react-router-dom'
import AppShell from './layout/AppShell.jsx'
import UnifiedChatPage from './pages/UnifiedChatPage.jsx'
import BusinessPage from './pages/BusinessPage.jsx'
import BIPage from './pages/BIPage.jsx'
import DocumentGeneratorPage from './pages/DocumentGeneratorPage.jsx'
import ProjectKnowledgeExpertPage from './pages/ProjectKnowledgeExpertPage.jsx'
import SettingsPage from './pages/Settings.jsx'
import HelpPage from './pages/Help.jsx'
import { API_BASE } from './api/client.js'

function AssistantHome() {
  const {
    assistantSession, resetAssistantChats, switchAssistantUser, scrollHeaders,
  } = useOutletContext()

  const token = assistantSession?.token
  const [capability, setCapability] = useState(null)
  const [view, setView] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    if (!token) return
    const controller = new AbortController()

    async function load() {
      try {
        const options = {
          cache: 'no-store',
          signal: controller.signal,
          headers: { Authorization: `Bearer ${token}` },
        }
        const response = await fetch(
          `${API_BASE}/api/v1/access`, options
        )

        if (response.status === 401 || response.status === 403) {
          switchAssistantUser(
            'Your session or access changed. Please open the assistant again.'
          )
          return
        }
        if (!response.ok) {
          throw new Error('Could not check your current access.')
        }

        const access = await response.json()
        const pairs = access.active_pairs || []
        let templates = []

        if (pairs.some(pair => pair.feature === 'document_generator')) {
          const result = await fetch(
            `${API_BASE}/api/v1/documents/templates`, options
          )
          if (result.status === 401) {
            switchAssistantUser(
              'Session expired. Please open the assistant again.'
            )
            return
          }
          if (result.ok) {
            templates = (await result.json()).templates || []
          } else if (result.status !== 403) {
            throw new Error('Could not load document templates.')
          }
        }

        if (!controller.signal.aborted) {
          setCapability({ token, pairs, templates })
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setCapability({ token, error: error.message })
        }
      }
    }

    load()
    const timer = setInterval(load, 30000)
    window.addEventListener('focus', load)

    return () => {
      controller.abort()
      clearInterval(timer)
      window.removeEventListener('focus', load)
    }
  }, [token, retry])

  if (!capability || capability.token !== token) {
    return <p className="p-6 text-sm">Checking access…</p>
  }

  if (capability.error) {
    return (
      <div className="p-6 text-sm" role="alert">
        <p>{capability.error}</p>
        <button
          className="mt-3 text-primary"
          onClick={() => {
            setCapability(null)
            setRetry(value => value + 1)
          }}
        >
          Retry
        </button>
      </div>
    )
  }

  const has = feature => (
    capability.pairs.some(pair => pair.feature === feature)
  )
  const hasTickets = (
    has('support_expert') &&
    assistantSession?.user.permissions?.includes('tickets.read')
  )

  const tabs = [
    ...(has('support_expert') || has('implementation_expert')
      ? [{ key: 'knowledge', label: 'Document expert' }] : []),
    ...(capability.pairs.some(pair => pair.feature === 'project_knowledge_expert' && pair.module === 'project')
      ? [{ key: 'company', label: 'Project Knowledge' }] : []),
    ...(has('business_lookup') || hasTickets
      ? [{ key: 'business', label: 'Business records' }] : []),
    ...(has('bi_expert')
      ? [{ key: 'bi', label: 'BI expert' }] : []),
    ...(capability.templates.length
      ? [{ key: 'generation', label: 'Document generator' }] : []),
  ]

  const active = tabs.some(tab => tab.key === view)
    ? view : tabs[0]?.key

  function renderFeatureTabs(content) {
    return scrollHeaders?.tabs
      ? createPortal(content, scrollHeaders.tabs)
      : content
  }

  function changeView(next) {
    if (next === active) return
    resetAssistantChats()
    setView(next)
  }

  return (
    <>
      {tabs.length > 1 && renderFeatureTabs(
        <div className="shrink-0 border-b border-border bg-surface px-4 py-2 flex flex-wrap gap-3 text-xs">
          {tabs.map(tab => (
            <button
              key={tab.key}
              type="button"
              onClick={() => changeView(tab.key)}
              className={
                active === tab.key
                  ? 'font-semibold text-primary'
                  : 'text-ink-secondary hover:text-primary'
              }
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {active === 'company'
        ? <ProjectKnowledgeExpertPage key={token} />
        : active === 'knowledge'
        ? <UnifiedChatPage key={token} licensedMode />
        : active === 'business'
          ? <BusinessPage key={token} />
          : active === 'bi'
            ? <BIPage key={token} />
            : active === 'generation'
              ? (
                <DocumentGeneratorPage
                  key={token}
                  templates={capability.templates}
                />
              )
              : (
                <p className="p-6">
                  No available feature is assigned to this user.
                </p>
              )}
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell licensedMode />}>
          <Route path="/" element={<AssistantHome />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}