import { NavLink } from 'react-router-dom'
import { Plus, MessageSquareText, Settings, HelpCircle, ChevronsLeft, ChevronsRight } from 'lucide-react'

const FOOTER_ITEMS = [
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/help', label: 'Help', icon: HelpCircle },
]

export default function Sidebar({ collapsed, onToggle, conversations, activeId, onNewChat, onSelectChat }) {
  return (
    <aside
      className={`shrink-0 h-full border-r border-border bg-surface flex flex-col transition-all duration-200 ${
        collapsed ? 'w-[68px]' : 'w-64'
      }`}
    >
      <div className="p-2.5">
        <button
          onClick={onNewChat}
          title={collapsed ? 'New chat' : undefined}
          className="w-full flex items-center gap-2 justify-center h-9 rounded-md bg-primary text-white
                     text-[13px] font-medium hover:bg-primary-dark transition-colors shadow-nav-glow"
        >
          <Plus className="w-4 h-4 shrink-0" strokeWidth={2} />
          {!collapsed && 'New chat'}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2.5 pb-2 flex flex-col gap-0.5">
        {!collapsed && (
          <div className="px-2.5 py-1.5 text-[10.5px] font-semibold text-ink-secondary/80 uppercase tracking-wide">
            Recent
          </div>
        )}
        {conversations.map((c) => (
          <button
            key={c.id}
            onClick={() => onSelectChat(c.id)}
            title={collapsed ? c.title : undefined}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-[13.5px] font-medium text-left
                        transition-all duration-150
              ${
                c.id === activeId
                  ? 'bg-primary/8 text-primary shadow-nav-glow'
                  : 'text-ink-secondary hover:bg-primary/5 hover:text-ink hover:shadow-nav-glow'
              }`}
          >
            <MessageSquareText className="w-4 h-4 shrink-0" strokeWidth={2} />
            {!collapsed && <span className="truncate flex-1">{c.title}</span>}
          </button>
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

function SidebarLink({ to, label, icon: Icon, collapsed }) {
  return (
    <NavLink
      to={to}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        `group flex items-center gap-3 px-3 py-2.5 rounded-md text-[13.5px] font-medium
         transition-all duration-150
         ${
           isActive
             ? 'bg-primary/8 text-primary shadow-nav-glow'
             : 'text-ink-secondary hover:bg-primary/5 hover:text-ink hover:shadow-nav-glow'
         }`
      }
    >
      <Icon className="w-4 h-4 shrink-0" strokeWidth={2} />
      {!collapsed && <span className="truncate">{label}</span>}
    </NavLink>
  )
}
