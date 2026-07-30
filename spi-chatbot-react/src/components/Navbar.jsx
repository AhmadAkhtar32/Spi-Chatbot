import { Box, User } from 'lucide-react'

export default function Navbar({ moduleLabel }) {
  return (
    <header className="h-14 shrink-0 border-b border-[#D1D5DB] bg-white flex items-center justify-between px-6 z-20">
      <div className="flex items-center gap-3">
        <div className="w-7 h-7 rounded-md bg-[#111827] flex items-center justify-center shrink-0">
          <Box className="w-4 h-4 text-white" strokeWidth={2} />
        </div>
        <div className="flex items-center gap-2 leading-none">
          <span className="text-[14px] font-semibold text-[#111827]">SPI ERP</span>
          <span className="w-px h-3.5 bg-[#D1D5DB]" />
          <span className="text-[13px] text-[#6B7280]">AI Assistant</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-[12px] font-medium text-[#2563EB] bg-[#2563EB]/8 border border-[#2563EB]/20 rounded px-2.5 py-1">
          {moduleLabel}
        </span>
        <div className="flex items-center gap-2 pl-3 border-l border-[#D1D5DB]">
          <span className="text-[13px] text-[#111827] font-medium hidden sm:inline">Minahil A.</span>
          <div className="w-7 h-7 rounded-full bg-slate-100 border border-[#D1D5DB] flex items-center justify-center">
            <User className="w-3.5 h-3.5 text-[#6B7280]" strokeWidth={2} />
          </div>
        </div>
      </div>
    </header>
  )
}
