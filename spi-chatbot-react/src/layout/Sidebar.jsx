import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  MessageSquareText,
  Wrench,
  LifeBuoy,
  FolderOpen,
  FileText,
  History,
  BarChart3,
  Settings,
  HelpCircle,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/bi-expert', label: 'BI Expert', icon: MessageSquareText },
  { to: '/implementation-expert', label: 'Implementation Expert', icon: Wrench },
  { to: '/support-expert', label: 'Support Expert', icon: LifeBuoy },
  { to: '/project-knowledge-expert', label: 'Project Knowledge Expert', icon: FolderOpen },
  { to: '/document-generator', label: 'Document Generator', icon: FileText },
  { to: '/history', label: 'Conversation History', icon: History },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/reports', label: 'Reports', icon: FileText },
]

const FOOTER_ITEMS = [
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/help', label: 'Help', icon: HelpCircle },
]

export default function Sidebar({ collapsed, onToggle }) {
  return (
    <aside
      className={`shrink-0 h-full border-r border-border bg-surface flex flex-col transition-all duration-200 ${
        collapsed ? 'w-[68px]' : 'w-64'
      }`}
    >
      <nav className="flex-1 overflow-y-auto py-4 px-2.5 flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => (
          <SidebarLink key={item.to} {...item} collapsed={collapsed} />
        ))}
      </nav>

      <div className="border-t border-border py-3 px-2.5 flex flex-col gap-0.5">
        {FOOTER_ITEMS.map((item) => (
          <SidebarLink key={item.to} {...item} collapsed={collapsed} />
        ))}
        <button
          onClick={onToggle}
          className="mt-1 flex items-center gap-3 px-3 py-2.5 rounded-md text-ink-secondary
                     hover:bg-slate-50 hover:text-ink transition-colors text-[13px] font-medium"
        >
          {collapsed ? <ChevronsRight className="w-4 h-4 shrink-0" /> : <ChevronsLeft className="w-4 h-4 shrink-0" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  )
}

function SidebarLink({ to, label, icon: Icon, end, comingSoon, collapsed }) {
  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        `group flex items-center gap-3 px-3 py-2.5 rounded-md text-[13.5px] font-medium transition-colors
         ${
           isActive
             ? 'bg-primary/8 text-primary'
             : 'text-ink-secondary hover:bg-slate-50 hover:text-ink'
         }`
      }
    >
      <Icon className="w-4 h-4 shrink-0" strokeWidth={2} />
      {!collapsed && (
        <span className="flex-1 flex items-center justify-between min-w-0">
          <span className="truncate">{label}</span>
          {comingSoon && (
            <span className="text-[9.5px] font-semibold tracking-wide text-ink-secondary/70 bg-slate-100 rounded px-1.5 py-0.5 shrink-0 ml-2">
              SOON
            </span>
          )}
        </span>
      )}
    </NavLink>
  )
}
