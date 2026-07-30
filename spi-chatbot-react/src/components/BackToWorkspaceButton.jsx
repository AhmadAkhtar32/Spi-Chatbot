import { ArrowLeft } from 'lucide-react'

export default function BackToWorkspaceButton({ onClick }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[#6B7280]
                 hover:text-[#111827] transition-colors duration-150
                 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]/40 rounded"
    >
      <ArrowLeft className="w-3.5 h-3.5" strokeWidth={2} />
      Back to Workspace
    </button>
  )
}
