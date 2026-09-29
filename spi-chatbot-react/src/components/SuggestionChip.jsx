import { ArrowUpRight } from 'lucide-react'

export default function SuggestionChip({
  icon: Icon,
  label,
  description,
  category = 'Financials',
  onClick,
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="
        group
        relative
        w-full
        text-left
        rounded-2xl
        border
        border-slate-200/80
        bg-white/85
        backdrop-blur-sm
        px-4
        py-4
        shadow-[0_2px_10px_rgba(15,23,42,0.03)]
        transition-all
        duration-200
        hover:-translate-y-0.5
        hover:border-blue-200
        hover:bg-white
        hover:shadow-[0_10px_30px_rgba(37,99,235,0.10)]
        focus:outline-none
        focus:ring-2
        focus:ring-blue-500/20
        active:translate-y-0
      "
    >
      <div className="flex items-start gap-3.5">
        {/* Icon */}
        <div
          className="
            flex
            h-10
            w-10
            shrink-0
            items-center
            justify-center
            rounded-xl
            bg-blue-50
            text-blue-600
            transition-all
            duration-200
            group-hover:bg-blue-600
            group-hover:text-white
          "
        >
          <Icon size={18} strokeWidth={1.8} />
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1 pr-5">
          <div
            className="
              mb-1
              text-[10px]
              font-semibold
              uppercase
              tracking-[0.12em]
              text-blue-600
            "
          >
            {category}
          </div>

          <div
            className="
              text-[14px]
              font-semibold
              leading-5
              text-slate-800
              transition-colors
              group-hover:text-blue-700
            "
          >
            {label}
          </div>

          {description && (
            <div
              className="
                mt-1
                text-[12px]
                leading-4
                text-slate-500
              "
            >
              {description}
            </div>
          )}
        </div>

        {/* Arrow */}
        <div
          className="
            absolute
            right-4
            top-4
            flex
            h-7
            w-7
            items-center
            justify-center
            rounded-full
            text-slate-300
            transition-all
            duration-200
            group-hover:bg-blue-50
            group-hover:text-blue-600
          "
        >
          <ArrowUpRight
            size={15}
            strokeWidth={2}
            className="
              transition-transform
              duration-200
              group-hover:translate-x-0.5
              group-hover:-translate-y-0.5
            "
          />
        </div>
      </div>
    </button>
  )
}