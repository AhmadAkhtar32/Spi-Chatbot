import { BrowserRouter, Routes, Route } from 'react-router-dom'
import AppShell from './layout/AppShell.jsx'
import Dashboard from './pages/Dashboard.jsx'
import BIExpertPage from './pages/BIExpertPage.jsx'
import ImplementationExpertPage from './pages/ImplementationExpertPage.jsx'
import SupportExpertPage from './pages/SupportExpertPage.jsx'
import HistoryPage from './pages/History.jsx'
import AnalyticsPage from './pages/Analytics.jsx'
import ReportsPage from './pages/Reports.jsx'
import SettingsPage from './pages/Settings.jsx'
import HelpPage from './pages/Help.jsx'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/bi-expert" element={<BIExpertPage />} />
          <Route path="/implementation-expert" element={<ImplementationExpertPage />} />
          <Route path="/support-expert" element={<SupportExpertPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/help" element={<HelpPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
