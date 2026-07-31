export default function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex-1 flex items-center justify-center py-16 px-6">
      <div className="text-center max-w-sm">
        <div className="w-11 h-11 rounded-lg bg-slate-100 flex items-center justify-center mx-auto mb-4">
          <Icon className="w-5 h-5 text-ink-secondary" strokeWidth={2} />
        </div>
        <h3 className="text-[14.5px] font-semibold text-ink mb-1.5">{title}</h3>
        <p className="text-[13px] text-ink-secondary leading-relaxed mb-5">{description}</p>
        {action}
      </div>
    </div>
  )
}
