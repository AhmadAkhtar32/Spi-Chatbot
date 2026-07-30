import { motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'

export default function ModuleCard({ icon: Icon, iconBg, iconColor, title, items, onClick }) {
  return (
    <motion.button
      onClick={onClick}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.15, ease: 'easeOut' }}
      className="group text-left bg-white border border-[#D1D5DB] rounded-lg p-5
                 hover:border-[#2563EB]/40 hover:shadow-[0_4px_16px_-4px_rgba(17,24,39,0.10)]
                 transition-shadow duration-150 focus:outline-none
                 focus-visible:ring-2 focus-visible:ring-[#2563EB]/40"
    >
      <div className="flex items-start justify-between mb-3.5">
        <span
          className="flex items-center justify-center w-9 h-9 rounded-md shrink-0"
          style={{ backgroundColor: iconBg }}
        >
          <Icon className="w-4.5 h-4.5" style={{ color: iconColor }} size={18} strokeWidth={2} />
        </span>
        <ArrowRight
          className="w-4 h-4 text-[#9CA3AF] mt-1 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-[#2563EB]"
          strokeWidth={2}
        />
      </div>

      <h3 className="text-[14.5px] font-semibold text-[#111827] mb-1.5">{title}</h3>
      <ul className="space-y-0.5">
        {items.map((item) => (
          <li key={item} className="text-[12.5px] text-[#6B7280] leading-relaxed">
            {item}
          </li>
        ))}
      </ul>
    </motion.button>
  )
}
