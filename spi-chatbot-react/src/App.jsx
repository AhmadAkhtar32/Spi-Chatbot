import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppShell from './layout/AppShell.jsx'
import UnifiedChatPage from './pages/UnifiedChatPage.jsx'
import ProjectKnowledgeExpertPage from './pages/ProjectKnowledgeExpertPage.jsx'
import DocumentGeneratorPage from './pages/DocumentGeneratorPage.jsx'
import ReportsPage from './pages/Reports.jsx'
import SettingsPage from './pages/Settings.jsx'
import HelpPage from './pages/Help.jsx'

export default function App() {
  const demoMode = import.meta.env.VITE_DEMO_MODE === '1'

  return (
    <BrowserRouter>
      <Routes>
        {demoMode ? (
          <Route element={<AppShell demoMode />}>
            <Route path="/" element={<UnifiedChatPage demoMode />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/help" element={<HelpPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        ) : (
          <Route element={<AppShell />}>
            <Route path="/" element={<UnifiedChatPage />} />
            <Route path="/project-knowledge-expert" element={<ProjectKnowledgeExpertPage />} />
            <Route path="/document-generator" element={<DocumentGeneratorPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/help" element={<HelpPage />} />
          </Route>
        )}
      </Routes>
    </BrowserRouter>
  )
}