import { PackageSearch, ClipboardList, Compass, BarChart3 } from 'lucide-react'
import SuggestionButton from './SuggestionButton.jsx'

const SUGGESTIONS = [
  { icon: PackageSearch, label: 'Check stock availability', prompt: "What's the stock of Pepsi?" },
  { icon: ClipboardList, label: 'Order status', prompt: "What's the status of order #1234?" },
  { icon: Compass, label: 'Find Purchase Order screen', prompt: 'Where do I create a purchase order?' },
  { icon: BarChart3, label: 'Inventory report', prompt: 'Show me the inventory stock report' },
]

export default function WelcomeState({ onSuggestion }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6">
      <div className="max-w-xl w-full text-center">
        <h1 className="text-[22px] font-semibold text-ink mb-2">SPI AI Assistant</h1>
        <p className="text-[14px] text-ink-secondary mb-8 leading-relaxed">
          Ask questions about inventory, sales, purchase orders, finance, payroll, or ERP navigation.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-left">
          {SUGGESTIONS.map((s) => (
            <SuggestionButton
              key={s.label}
              icon={s.icon}
              label={s.label}
              onClick={() => onSuggestion(s.prompt)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
