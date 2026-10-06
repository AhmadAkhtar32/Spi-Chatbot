import { NavLink, useLocation } from 'react-router-dom'
import {
  Plus,
  MessageSquareText,
  Settings,
  HelpCircle,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'

const FOOTER_ITEMS = [
  {
    to: '/settings',
    label: 'Settings',
    icon: Settings,
  },
  {
    to: '/help',
    label: 'Help',
    icon: HelpCircle,
  },
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
  const location = useLocation()

  const isChatPage = location.pathname === '/'

  return (
    <aside
      className={`
        fixed left-0 top-14 bottom-0 z-50
        w-64
        bg-surface
        border-r border-border
        flex flex-col
        transition-all duration-200 ease-out
        shadow-sm

        ${
          mobileOpen
            ? 'translate-x-0'
            : '-translate-x-full'
        }

        md:static
        md:top-auto
        md:bottom-auto
        md:z-auto
        md:h-full
        md:translate-x-0

        ${
          collapsed
            ? 'md:w-[68px]'
            : 'md:w-64'
        }
      `}
    >
      {/* New Chat */}
      <div className="p-2.5">
        <button
          type="button"
          onClick={onNewChat}
          title={collapsed ? 'New chat' : undefined}
          className="
            w-full
            h-9
            rounded-lg
            bg-primary
            text-white
            flex
            items-center
            justify-center
            gap-2
            text-[13px]
            font-semibold
            hover:bg-primary-dark
            transition-all
            duration-150
            shadow-nav-glow
          "
        >
          <Plus
            className="w-4 h-4 shrink-0"
            strokeWidth={2}
          />

          <span
            className={
              collapsed
                ? 'md:hidden'
                : ''
            }
          >
            New chat
          </span>
        </button>
      </div>

      {/* Recent Chats */}
      <nav className="flex-1 overflow-y-auto px-2.5 pb-3">
        <div
          className={`
            px-2.5
            pt-2
            pb-2
            text-[10.5px]
            font-semibold
            text-ink-secondary/70
            uppercase
            tracking-[0.08em]

            ${collapsed ? 'md:hidden' : ''}
          `}
        >
          Recent
        </div>

        <div className="flex flex-col gap-0.5">
          {conversations.map((conversation) => {
            const active =
              isChatPage &&
              conversation.id === activeId

            return (
              <button
                type="button"
                key={conversation.id}
                onClick={() =>
                  onSelectChat(conversation.id)
                }
                title={
                  collapsed
                    ? conversation.title
                    : undefined
                }
                className={`
                  group
                  w-full
                  flex
                  items-center
                  gap-3
                  px-3
                  py-2.5
                  rounded-lg
                  text-left
                  text-[13.5px]
                  font-medium
                  transition-all
                  duration-150

                  ${
                    active
                      ? 'bg-primary/10 text-primary'
                      : 'text-ink-secondary hover:bg-hover hover:text-ink'
                  }
                `}
              >
                <MessageSquareText
                  className={`
                    w-4 h-4
                    shrink-0

                    ${
                      active
                        ? 'text-primary'
                        : 'text-ink-secondary'
                    }
                  `}
                  strokeWidth={2}
                />

                <span
                  className={`
                    truncate flex-1
                    ${collapsed ? 'md:hidden' : ''}
                  `}
                >
                  {conversation.title}
                </span>
              </button>
            )
          })}
        </div>
      </nav>

      {/* Footer */}
      <div className="border-t border-border p-2.5 flex flex-col gap-0.5">
        {FOOTER_ITEMS.map((item) => (
          <SidebarLink
            key={item.to}
            {...item}
            collapsed={collapsed}
            onNavigate={onMobileClose}
          />
        ))}

        <button
          type="button"
          onClick={onToggle}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="
            hidden md:flex
            items-center
            gap-3
            px-3
            py-2.5
            mt-1
            rounded-lg
            text-[13px]
            font-medium
            text-ink-secondary
            hover:bg-hover
            hover:text-ink
            transition-colors
          "
        >
          {collapsed ? (
            <ChevronsRight className="w-4 h-4 shrink-0" />
          ) : (
            <ChevronsLeft className="w-4 h-4 shrink-0" />
          )}

          {!collapsed && (
            <span>Collapse</span>
          )}
        </button>
      </div>
    </aside>
  )
}

function SidebarLink({
  to,
  label,
  icon: Icon,
  collapsed,
  onNavigate,
}) {
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        `
          flex
          items-center
          gap-3
          px-3
          py-2.5
          rounded-lg
          text-[13.5px]
          font-medium
          transition-all
          duration-150

          ${
            isActive
              ? 'bg-primary/10 text-primary'
              : 'text-ink-secondary hover:bg-hover hover:text-ink'
          }
        `
      }
    >
      <Icon
        className="w-4 h-4 shrink-0"
        strokeWidth={2}
      />

      <span
        className={`
          truncate
          ${collapsed ? 'md:hidden' : ''}
        `}
      >
        {label}
      </span>
    </NavLink>
  )
}