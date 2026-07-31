export default function PageHeader({ title, description, action }) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div>
        <h1 className="text-[20px] font-semibold text-ink mb-1">{title}</h1>
        {description && <p className="text-[13.5px] text-ink-secondary max-w-2xl">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}
