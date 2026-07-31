export default function MetricCard({ icon: Icon, label, value, hint }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[12px] font-medium text-ink-secondary">{label}</span>
        <span className="w-7 h-7 rounded-md bg-primary/8 flex items-center justify-center">
          <Icon className="w-3.5 h-3.5 text-primary" strokeWidth={2} />
        </span>
      </div>
      <div className="text-[22px] font-semibold text-ink leading-none mb-1">{value}</div>
      {hint && <div className="text-[11.5px] text-ink-secondary">{hint}</div>}
    </div>
  )
}
