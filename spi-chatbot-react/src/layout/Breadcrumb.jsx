import { ChevronRight } from 'lucide-react'

export default function Breadcrumb({ items }) {
  return (
    // Hidden on phones: the page title already tells the user where they are
    <div className="hidden md:flex items-center gap-1.5 text-[12.5px] text-ink-secondary mb-1 min-w-0">
      {items.map((item, i) => (
        <span key={item} className="flex items-center gap-1.5 min-w-0">
          {i > 0 && <ChevronRight className="w-3 h-3 shrink-0" />}
          <span className={`truncate ${i === items.length - 1 ? 'text-ink font-medium' : ''}`}>{item}</span>
        </span>
      ))}
    </div>
  )
}