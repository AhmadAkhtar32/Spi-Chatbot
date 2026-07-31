export default function SuggestionChip({ icon: Icon, label, onClick }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 px-3.5 py-2 rounded-md border border-border bg-surface
                 text-[12.5px] font-medium text-ink-secondary hover:border-primary/40 hover:text-primary
                 transition-colors"
    >
      {Icon && <Icon className="w-3.5 h-3.5" strokeWidth={2} />}
      {label}
    </button>
  )
}
