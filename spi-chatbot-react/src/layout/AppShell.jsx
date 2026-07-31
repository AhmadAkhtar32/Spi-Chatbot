import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import TopBar from './TopBar.jsx'
import Sidebar from './Sidebar.jsx'

export default function AppShell() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="h-screen flex flex-col bg-bg">
      <TopBar />
      <div className="flex-1 flex min-h-0">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />
        <main className="flex-1 min-w-0 flex flex-col">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
