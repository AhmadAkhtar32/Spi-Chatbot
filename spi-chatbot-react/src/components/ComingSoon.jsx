import { Clock } from 'lucide-react'

export default function ComingSoon({ icon: Icon, title, description, points }) {
  return (
    <div className="flex-1 flex items-center justify-center px-6 py-12">
      <div className="max-w-md w-full text-center">
        <div className="w-12 h-12 rounded-lg bg-primary/8 flex items-center justify-center mx-auto mb-5">
          <Icon className="w-6 h-6 text-primary" strokeWidth={2} />
        </div>

        <div className="inline-flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-primary bg-primary/8 border border-primary/20 rounded-full px-3 py-1 mb-4">
          <Clock className="w-3 h-3" />
          COMING SOON
        </div>

        <h2 className="text-[18px] font-semibold text-ink mb-2">{title}</h2>
        <p className="text-[13.5px] text-ink-secondary leading-relaxed mb-6">{description}</p>

        {points && (
          <div className="card p-4 text-left">
            <div className="text-[11.5px] font-semibold text-ink-secondary uppercase tracking-wide mb-2.5">
              Backend status
            </div>
            <ul className="space-y-2">
              {points.map((point) => (
                <li key={point} className="flex items-start gap-2 text-[13px] text-ink">
                  <span className="w-1.5 h-1.5 rounded-full bg-success mt-1.5 shrink-0" />
                  {point}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
