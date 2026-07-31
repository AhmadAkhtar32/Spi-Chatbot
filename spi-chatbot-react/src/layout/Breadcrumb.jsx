import { ChevronRight } from 'lucide-react'

export default function Breadcrumb({ items }) {
  return (
    <div className="flex items-center gap-1.5 text-[12.5px] text-ink-secondary mb-1">
      {items.map((item, i) => (
        <span key={item} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight className="w-3 h-3" />}
          <span className={i === items.length - 1 ? 'text-ink font-medium' : ''}>{item}</span>
        </span>
      ))}
    </div>
  )
}
