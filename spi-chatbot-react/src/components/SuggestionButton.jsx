export default function SuggestionButton({ icon: Icon, label, onClick }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-3 text-left px-4 py-3.5 bg-surface border border-border rounded-md
                 hover:border-primary/40 hover:bg-slate-50 transition-colors duration-150
                 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
    >
      <span className="flex items-center justify-center w-8 h-8 rounded-md bg-slate-100 shrink-0">
        <Icon className="w-4 h-4 text-ink-secondary" strokeWidth={2} />
      </span>
      <span className="text-[13.5px] font-medium text-ink">{label}</span>
    </button>
  )
}
