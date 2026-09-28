import { NavLink } from 'react-router-dom'
import { Plus, MessageSquareText, Settings, HelpCircle, ChevronsLeft, ChevronsRight, X } from 'lucide-react'

const FOOTER_ITEMS = [
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/help', label: 'Help', icon: HelpCircle },
]

export default function Sidebar({
  collapsed,
  onToggle,
  mobileOpen,
  onMobileClose,
  conversations,
  activeId,
  onNewChat,
  onSelectChat,
}) {
  // "collapsed" only applies from md upward. On mobile the drawer always
  // shows full labels, so we hide labels with `md:hidden` instead of
  // removing them from the DOM.
  const hideOnCollapse = collapsed ? 'md:hidden' : ''

  return (
    <aside
      className={`
        fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] h-full
        border-r border-border bg-surface flex flex-col shadow-xl
        transition-transform duration-200 ease-out
        ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
        md:static md:z-auto md:max-w-none md:shrink-0 md:shadow-none
        md:translate-x-0 md:transition-all
        ${collapsed ? 'md:w-[68px]' : 'md:w-64'}
      `}
    >
      {/* Mobile-only header with close button */}
      <div className="md:hidden flex items-center justify-between px-4 pt-3 pb-1">
        <span className="text-[13px] font-semibold text-ink">Conversations</span>
        <button
          onClick={onMobileClose}
          aria-label="Close menu"
          className="w-8 h-8 rounded-md flex items-center justify-center text-ink-secondary hover:bg-slate-50"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-2.5">
        <button
          onClick={onNewChat}
          title={collapsed ? 'New chat' : undefined}
          className="w-full flex items-center gap-2 justify-center h-10 md:h-9 rounded-md bg-primary text-white
                     text-[13px] font-medium hover:bg-primary-dark transition-colors shadow-nav-glow"
        >
          <Plus className="w-4 h-4 shrink-0" strokeWidth={2} />
          <span className={hideOnCollapse}>New chat</span>
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2.5 pb-2 flex flex-col gap-0.5">
        <div
          className={`px-2.5 py-1.5 text-[10.5px] font-semibold text-ink-secondary/80 uppercase tracking-wide ${hideOnCollapse}`}
        >
          Recent
        </div>
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
            <span className={`truncate flex-1 ${hideOnCollapse}`}>{c.title}</span>
          </button>
        ))}
      </nav>

      <div className="border-t border-border py-3 px-2.5 flex flex-col gap-0.5 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        {FOOTER_ITEMS.map((item) => (
          <SidebarLink
            key={item.to}
            {...item}
            collapsed={collapsed}
            hideOnCollapse={hideOnCollapse}
            onNavigate={onMobileClose}
          />
        ))}
        {/* Collapse toggle is desktop-only; on mobile the drawer has a close button */}
        <button
          onClick={onToggle}
          className="hidden md:flex mt-1 items-center gap-3 px-3 py-2.5 rounded-md text-ink-secondary
                     hover:bg-slate-50 hover:text-ink transition-colors text-[13px] font-medium"
        >
          {collapsed ? <ChevronsRight className="w-4 h-4 shrink-0" /> : <ChevronsLeft className="w-4 h-4 shrink-0" />}
          <span className={hideOnCollapse}>Collapse</span>
        </button>
      </div>
    </aside>
  )
}

function SidebarLink({ to, label, icon: Icon, collapsed, hideOnCollapse, onNavigate }) {
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
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
      <span className={`truncate ${hideOnCollapse}`}>{label}</span>
    </NavLink>
  )
}