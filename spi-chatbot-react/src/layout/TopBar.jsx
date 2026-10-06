import {
  useEffect,
  useRef,
  useState,
} from 'react'

import {
  useLocation,
  useNavigate,
} from 'react-router-dom'

import {
  Bell,
  Settings,
  Sun,
  Moon,
  ChevronDown,
  User,
  Menu,
} from 'lucide-react'

const THEME_KEY = 'spi-theme'

function getInitialTheme() {
  try {
    const saved = localStorage.getItem(THEME_KEY)

    if (saved === 'light' || saved === 'dark') {
      return saved
    }
  } catch {
    // ignore
  }

  return window.matchMedia?.(
    '(prefers-color-scheme: dark)'
  ).matches
    ? 'dark'
    : 'light'
}

export default function TopBar({
  onMenuClick,
}) {
  const navigate = useNavigate()
  const location = useLocation()

  const [theme, setTheme] =
    useState(getInitialTheme)

  const [notifOpen, setNotifOpen] =
    useState(false)

  const [profileOpen, setProfileOpen] =
    useState(false)

  const notificationRef = useRef(null)
  const profileRef = useRef(null)

  // Apply theme globally
  useEffect(() => {
    const root = document.documentElement

    const isDark = theme === 'dark'

    root.classList.toggle('dark', isDark)

    root.style.colorScheme =
      isDark ? 'dark' : 'light'

    try {
      localStorage.setItem(
        THEME_KEY,
        theme
      )
    } catch {
      // ignore
    }
  }, [theme])

  // Outside click + Escape
  useEffect(() => {
    function handleMouseDown(event) {
      if (
        notificationRef.current &&
        !notificationRef.current.contains(
          event.target
        )
      ) {
        setNotifOpen(false)
      }

      if (
        profileRef.current &&
        !profileRef.current.contains(
          event.target
        )
      ) {
        setProfileOpen(false)
      }
    }

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setNotifOpen(false)
        setProfileOpen(false)
      }
    }

    document.addEventListener(
      'mousedown',
      handleMouseDown
    )

    document.addEventListener(
      'keydown',
      handleKeyDown
    )

    return () => {
      document.removeEventListener(
        'mousedown',
        handleMouseDown
      )

      document.removeEventListener(
        'keydown',
        handleKeyDown
      )
    }
  }, [])

  // Close menus on navigation
  useEffect(() => {
    setNotifOpen(false)
    setProfileOpen(false)
  }, [location.pathname])

  function toggleTheme() {
    setTheme((current) =>
      current === 'dark'
        ? 'light'
        : 'dark'
    )
  }

  function toggleNotifications() {
    setNotifOpen((current) => !current)
    setProfileOpen(false)
  }

  function toggleProfile() {
    setProfileOpen((current) => !current)
    setNotifOpen(false)
  }

  function goToSettings() {
    setNotifOpen(false)
    setProfileOpen(false)
    navigate('/settings')
  }

  return (
    <header
      className="
        h-14
        shrink-0
        border-b border-border
        bg-surface
        flex
        items-center
        justify-between
        px-3 sm:px-5
        z-30
        relative
      "
    >
      {/* Left */}
      <div className="flex items-center gap-2.5 min-w-0">
        <button
          type="button"
          onClick={onMenuClick}
          className="
            md:hidden
            w-8 h-8
            rounded-lg
            flex
            items-center
            justify-center
            text-ink-secondary
            hover:bg-hover
            hover:text-ink
            transition-colors
          "
          aria-label="Open navigation"
        >
          <Menu
            className="w-4.5 h-4.5"
            strokeWidth={2}
          />
        </button>

        <div
          className="
            w-7 h-7
            rounded-lg
            bg-primary
            flex
            items-center
            justify-center
            shrink-0
          "
        >
          <span className="text-white text-[12px] font-bold">
            S
          </span>
        </div>

        <div className="flex items-center gap-2 leading-none min-w-0">
          <span className="text-[14px] font-semibold text-ink">
            SPI
          </span>

          <span className="hidden sm:block w-px h-3.5 bg-border" />

          <span className="hidden sm:block text-[13px] text-ink-secondary truncate">
            Enterprise AI Assistant
          </span>
        </div>
      </div>

      <div className="flex-1" />

      {/* Right */}
      <div className="flex items-center gap-1.5">
        {/* Theme */}
        <button
          type="button"
          onClick={toggleTheme}
          title={
            theme === 'dark'
              ? 'Switch to light mode'
              : 'Switch to dark mode'
          }
          className="
            flex
            items-center
            gap-1.5
            px-2.5
            h-8
            rounded-lg
            border border-border
            text-[11.5px]
            text-ink-secondary
            hover:bg-hover
            hover:text-ink
            transition-colors
          "
        >
          {theme === 'dark' ? (
            <Moon className="w-3.5 h-3.5" />
          ) : (
            <Sun className="w-3.5 h-3.5" />
          )}

          <span className="hidden sm:inline">
            {theme === 'dark'
              ? 'Dark'
              : 'Light'}
          </span>
        </button>

        {/* Settings */}
        <IconButton
          title="Settings"
          onClick={goToSettings}
        >
          <Settings
            className="w-4 h-4"
            strokeWidth={2}
          />
        </IconButton>

        {/* Notifications */}
        <div
          ref={notificationRef}
          className="relative"
        >
          <IconButton
            title="Notifications"
            onClick={toggleNotifications}
          >
            <Bell
              className="w-4 h-4"
              strokeWidth={2}
            />
          </IconButton>

          {notifOpen && (
            <div
              className="
                absolute
                right-0
                top-11
                w-72
                max-w-[calc(100vw-20px)]
                bg-surface
                border border-border
                rounded-xl
                shadow-xl
                overflow-hidden
                z-50
              "
            >
              <div className="px-4 py-3 border-b border-border">
                <p className="text-[13px] font-semibold text-ink">
                  Notifications
                </p>
              </div>

              <div className="px-4 py-8 text-center">
                <div
                  className="
                    w-9 h-9
                    mx-auto
                    mb-2.5
                    rounded-full
                    bg-muted
                    flex items-center
                    justify-center
                  "
                >
                  <Bell className="w-4 h-4 text-ink-secondary" />
                </div>

                <p className="text-[12.5px] font-medium text-ink">
                  You're all caught up
                </p>

                <p className="text-[11.5px] text-ink-secondary mt-1">
                  No new notifications
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Profile */}
        <div
          ref={profileRef}
          className="relative ml-0.5"
        >
          <button
            type="button"
            onClick={toggleProfile}
            className="
              flex
              items-center
              gap-1.5
              pl-1
              pr-2
              py-1
              rounded-lg
              hover:bg-hover
              transition-colors
            "
          >
            <div
              className="
                w-7 h-7
                rounded-full
                bg-muted
                border border-border
                flex
                items-center
                justify-center
              "
            >
              <User
                className="w-3.5 h-3.5 text-ink-secondary"
                strokeWidth={2}
              />
            </div>

            <ChevronDown
              className={`
                w-3.5 h-3.5
                text-ink-secondary
                transition-transform
                duration-150

                ${
                  profileOpen
                    ? 'rotate-180'
                    : ''
                }
              `}
            />
          </button>

          {profileOpen && (
            <div
              className="
                absolute
                right-0
                top-11
                w-56
                bg-surface
                border border-border
                rounded-xl
                shadow-xl
                overflow-hidden
                z-50
              "
            >
              <div className="px-3.5 py-3 border-b border-border">
                <div className="flex items-center gap-2.5">
                  <div
                    className="
                      w-9 h-9
                      rounded-full
                      bg-muted
                      border border-border
                      flex
                      items-center
                      justify-center
                    "
                  >
                    <User className="w-4 h-4 text-ink-secondary" />
                  </div>

                  <div>
                    <p className="text-[13px] font-semibold text-ink">
                      SPI User
                    </p>

                    <p className="text-[11.5px] text-ink-secondary">
                      Enterprise Assistant
                    </p>
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={goToSettings}
                className="
                  w-full
                  flex
                  items-center
                  gap-2.5
                  px-3.5
                  py-2.5
                  text-[13px]
                  text-ink-secondary
                  hover:bg-hover
                  hover:text-ink
                  transition-colors
                "
              >
                <Settings className="w-3.5 h-3.5" />
                Settings
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

function IconButton({
  children,
  title,
  onClick,
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="
        relative
        w-8 h-8
        rounded-lg
        flex
        items-center
        justify-center
        text-ink-secondary
        hover:bg-hover
        hover:text-ink
        transition-colors
      "
    >
      {children}
    </button>
  )
}