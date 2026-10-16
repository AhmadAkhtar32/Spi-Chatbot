import { useState } from 'react'
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useOutletContext,
} from 'react-router-dom'

import AppShell from './layout/AppShell.jsx'
import UnifiedChatPage from './pages/UnifiedChatPage.jsx'
import DemoBusinessPage from './pages/DemoBusinessPage.jsx'
import ProjectKnowledgeExpertPage from './pages/ProjectKnowledgeExpertPage.jsx'
import DocumentGeneratorPage from './pages/DocumentGeneratorPage.jsx'
import ReportsPage from './pages/Reports.jsx'
import SettingsPage from './pages/Settings.jsx'
import HelpPage from './pages/Help.jsx'

const BUSINESS_PERMISSIONS = [
  'stock.read',
  'sales_orders.read',
  'purchase_orders.read',
  'tickets.read',
  'payroll.read',
  'payroll.read_self',
]

function DemoHome() {
  const { demoSession, resetDemoChats } = useOutletContext()

  const hasDocumentExpert = demoSession?.user.experts?.some(
    (name) =>
      name === 'support_expert' ||
      name === 'implementation_expert'
  )

  const hasBusinessData = demoSession?.user.permissions?.some(
    (name) => BUSINESS_PERMISSIONS.includes(name)
  )

  const [view, setView] = useState(
    hasDocumentExpert ? 'documents' : 'business'
  )

  function changeView(next) {
    if (next === view) return

    resetDemoChats()
    setView(next)
  }

  return (
    <>
      {hasDocumentExpert && hasBusinessData && (
        <div className="shrink-0 border-b border-border bg-surface px-4 py-2 flex gap-2 text-xs">
          <button
            type="button"
            onClick={() => changeView('documents')}
            className={
              view === 'documents'
                ? 'font-semibold text-primary'
                : 'text-ink-secondary hover:text-primary'
            }
          >
            Document expert
          </button>

          <span className="text-border">|</span>

          <button
            type="button"
            onClick={() => changeView('business')}
            className={
              view === 'business'
                ? 'font-semibold text-primary'
                : 'text-ink-secondary hover:text-primary'
            }
          >
            Business records
          </button>
        </div>
      )}

      {view === 'documents' && hasDocumentExpert ? (
        <UnifiedChatPage demoMode />
      ) : (
        <DemoBusinessPage />
      )}
    </>
  )
}

export default function App() {
  const demoMode = import.meta.env.VITE_DEMO_MODE === '1'

  return (
    <BrowserRouter>
      <Routes>
        {demoMode ? (
          <Route element={<AppShell demoMode />}>
            <Route path="/" element={<DemoHome />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/help" element={<HelpPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        ) : (
          <Route element={<AppShell />}>
            <Route path="/" element={<UnifiedChatPage />} />
            <Route
              path="/project-knowledge-expert"
              element={<ProjectKnowledgeExpertPage />}
            />
            <Route
              path="/document-generator"
              element={<DocumentGeneratorPage />}
            />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/help" element={<HelpPage />} />
          </Route>
        )}
      </Routes>
    </BrowserRouter>
  )
}