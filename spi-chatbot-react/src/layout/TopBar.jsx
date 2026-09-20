import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Bell, Settings, Sun, ChevronDown, User, LogOut } from 'lucide-react'

export default function TopBar() {
  const navigate = useNavigate()
  const [notifOpen, setNotifOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)

  return (
    <header className="h-14 shrink-0 border-b border-border bg-surface flex items-center justify-between px-5 z-30 relative">
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-7 h-7 rounded-md bg-primary flex items-center justify-center shrink-0">
          <span className="text-white text-[12px] font-bold">S</span>
        </div>
        <div className="flex items-center gap-2 leading-none min-w-0">
          <span className="text-[14px] font-semibold text-ink truncate">SPI</span>
          <span className="w-px h-3.5 bg-border shrink-0" />
          <span className="text-[13px] text-ink-secondary truncate">Enterprise AI Assistant</span>
        </div>
      </div>

      <div className="hidden md:flex flex-1 max-w-md mx-6 relative">
        <Search className="w-4 h-4 text-ink-secondary absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          placeholder="Search conversations, reports, settings..."
          className="w-full h-9 pl-9 pr-3 rounded-md border border-border bg-bg text-[13px] text-ink
                     placeholder:text-ink-secondary/70 focus:outline-none focus:border-primary focus:bg-surface transition-colors"
        />
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        <div
          className="hidden sm:flex items-center gap-1.5 text-[11.5px] text-ink-secondary px-2.5 py-1.5 rounded-md border border-border mr-1"
          title="Light mode only"
        >
          <Sun className="w-3.5 h-3.5" />
          Light
        </div>

        <IconButton title="Settings" onClick={() => navigate('/settings')}>
          <Settings className="w-4 h-4" strokeWidth={2} />
        </IconButton>

        <div className="relative">
          <IconButton title="Notifications" onClick={() => setNotifOpen((v) => !v)}>
            <Bell className="w-4 h-4" strokeWidth={2} />
            <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-danger" />
          </IconButton>
          {notifOpen && (
            <div className="absolute right-0 top-11 w-72 bg-surface border border-border rounded-md shadow-lg py-2 z-40">
              <div className="px-3 py-2 text-[12px] font-semibold text-ink border-b border-border">
                Notifications
              </div>
              <div className="px-3 py-6 text-center text-[12.5px] text-ink-secondary">
                You're all caught up — no new notifications.
              </div>
            </div>
          )}
        </div>

        <div className="relative ml-1">
          <button
            onClick={() => setProfileOpen((v) => !v)}
            className="flex items-center gap-2 pl-1 pr-2 py-1 rounded-md hover:bg-slate-50 transition-colors"
          >
            <div className="w-7 h-7 rounded-full bg-slate-100 border border-border flex items-center justify-center">
              <User className="w-3.5 h-3.5 text-ink-secondary" strokeWidth={2} />
            </div>
            
            <ChevronDown className="w-3.5 h-3.5 text-ink-secondary" strokeWidth={2} />
          </button>
          {profileOpen && (
            <div className="absolute right-0 top-11 w-56 bg-surface border border-border rounded-md shadow-lg py-1.5 z-40">
              <div className="px-3 py-2 border-b border-border">
              <User className="w-4 h-4 text-ink-secondary" />
            </div>
              <button className="w-full text-left px-3 py-2 text-[13px] text-ink-secondary hover:bg-slate-50 flex items-center gap-2">
                <User className="w-3.5 h-3.5" /> Profile
              </button>
              <button
                onClick={() => navigate('/settings')}
                className="w-full text-left px-3 py-2 text-[13px] text-ink-secondary hover:bg-slate-50 flex items-center gap-2"
              >
                <Settings className="w-3.5 h-3.5" /> Settings
              </button>
              <button className="w-full text-left px-3 py-2 text-[13px] text-danger hover:bg-slate-50 flex items-center gap-2 border-t border-border mt-1 pt-2">
                <LogOut className="w-3.5 h-3.5" /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

function IconButton({ children, title, onClick }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="relative w-8 h-8 rounded-md flex items-center justify-center text-ink-secondary
                 hover:bg-slate-50 hover:text-ink transition-colors"
    >
      {children}
    </button>
  )
}
