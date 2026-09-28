export default function PageHeader({ title, description, action }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 sm:gap-4 mb-4 sm:mb-6">
      <div className="min-w-0">
        <h1 className="text-[18px] sm:text-[20px] font-semibold text-ink mb-1 break-words">{title}</h1>
        {description && (
          <p className="text-[13px] sm:text-[13.5px] text-ink-secondary max-w-2xl">{description}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}