const STYLES = {
  success: 'bg-success/10 text-success border-success/25',
  warning: 'bg-warning/10 text-warning border-warning/25',
  error: 'bg-danger/10 text-danger border-danger/25',
}

export default function StatusBadge({ type = 'success', label }) {
  const style = STYLES[type] || STYLES.success
  return (
    <span
      className={`inline-flex items-center gap-1.5 border rounded px-2 py-0.5 text-[12px] font-medium align-middle ${style}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          type === 'success' ? 'bg-success' : type === 'warning' ? 'bg-warning' : 'bg-danger'
        }`}
      />
      {label}
    </span>
  )
}
