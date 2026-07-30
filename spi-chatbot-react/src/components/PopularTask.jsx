import { ArrowUpRight } from 'lucide-react'

export default function PopularTask({ label, onClick }) {
  return (
    <button
      onClick={onClick}
      className="group w-full flex items-center justify-between px-4 py-2.5 rounded-md
                 hover:bg-slate-50 transition-colors duration-150 text-left
                 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]/40"
    >
      <span className="text-[13.5px] text-[#111827]">{label}</span>
      <ArrowUpRight
        className="w-3.5 h-3.5 text-[#9CA3AF] opacity-0 group-hover:opacity-100 transition-opacity duration-150"
        strokeWidth={2}
      />
    </button>
  )
}
