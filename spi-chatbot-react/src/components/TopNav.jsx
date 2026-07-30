import { Box, User } from 'lucide-react'

export default function TopNav() {
  return (
    <header className="h-16 shrink-0 border-b border-border bg-surface flex items-center justify-between px-6">
      <div className="flex items-center gap-3">
        {/* Logo placeholder — swap for the real D-Bizz mark */}
        <div className="w-8 h-8 rounded-md bg-ink flex items-center justify-center">
          <Box className="w-4.5 h-4.5 text-white" size={18} strokeWidth={2} />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[15px] font-semibold text-ink leading-none">SPI</span>
          <span className="w-px h-4 bg-border" />
          <span className="text-[13px] text-ink-secondary leading-none">AI Assistant</span>
        </div>
      </div>

      <div className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-100 border border-border">
        <User className="w-4 h-4 text-ink-secondary" strokeWidth={2} />
      </div>
    </header>
  )
}
